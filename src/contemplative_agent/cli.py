"""CLI entry point for the Contemplative Agent."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass, field
import hashlib
import json as json_mod
import logging
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Optional, Sequence, cast

if TYPE_CHECKING:
    from .core.views import ViewRegistry
from xml.sax.saxutils import escape as xml_escape

from .adapters.moltbook.agent import Agent, AutonomyLevel
from .adapters.moltbook.config import (
    CONSTITUTION_DIR,
    DEFAULT_MOLTBOOK_HOME,
    EPISODE_LOG_DIR,
    IDENTITY_PATH,
    KNOWLEDGE_PATH,
    MEDITATION_DIR,
    MOLTBOOK_DATA_DIR,
    PROMPTS_DIR,
    REPORTS_DIR,
    RULES_DIR,
    RUN_LOCK_PATH,
    SKILLS_DIR,
    SNAPSHOTS_DIR,
    STAGED_DIR,
    VIEWS_DIR,
)
from .core._io import acquire_run_lock, append_jsonl_restricted, now_iso
from .core.domain import (
    DEFAULT_CONFIG_DIR,
    DomainConfig,
    get_domain_config,
    load_constitution,
    load_domain_config,
    reset_caches,
    set_domain_config_cache,
)
from .core.llm import configure as configure_llm

logger = logging.getLogger(__name__)


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


LAUNCHD_LABEL = "com.moltbook.agent"
LAUNCHD_DISTILL_LABEL = "com.moltbook.distill"
LAUNCHD_WEEKLY_ANALYSIS_LABEL = "com.moltbook.weekly-analysis"
LAUNCHD_PLIST_DIR = Path.home() / "Library" / "LaunchAgents"
LAUNCHD_PLIST_PATH = LAUNCHD_PLIST_DIR / f"{LAUNCHD_LABEL}.plist"
LAUNCHD_DISTILL_PLIST_PATH = LAUNCHD_PLIST_DIR / f"{LAUNCHD_DISTILL_LABEL}.plist"
LAUNCHD_WEEKLY_ANALYSIS_PLIST_PATH = LAUNCHD_PLIST_DIR / f"{LAUNCHD_WEEKLY_ANALYSIS_LABEL}.plist"


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


def _do_uninstall_schedule() -> None:
    """Uninstall launchd plists (session + distill + weekly-analysis)."""
    removed = False

    for plist_path, label in [
        (LAUNCHD_PLIST_PATH, "session"),
        (LAUNCHD_DISTILL_PLIST_PATH, "distill"),
        (LAUNCHD_WEEKLY_ANALYSIS_PLIST_PATH, "weekly-analysis"),
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


AUDIT_LOG_PATH = MOLTBOOK_DATA_DIR / "logs" / "audit.jsonl"


AuditSource = Literal[
    "direct",
    "stage",
    "stage-adopted",
    "stage-adopted-auto",
    "direct-remove",
    "direct-remove-auto",
]


def _log_approval(
    command: str,
    path: Path,
    approved: bool | None,
    content: str,
    *,
    source: AuditSource = "direct",
    snapshot_path: Optional[Path] = None,
    reason: Optional[str] = None,
    source_ids: Optional[Sequence[str]] = None,
    epistemic_counts: Optional[dict[str, int]] = None,
) -> None:
    """Append approval decision to audit log.

    Args:
        command: The CLI subcommand name (e.g. "insight", "rules-distill").
        path: Final target path for the generated content.
        approved: True = accepted, False = rejected, None = staged (not yet decided).
        content: Full text of the generated artifact (for hashing).
        source: Execution path identifier.
            - "direct": approval gate was invoked inline during the command run.
            - "stage": written to staging dir (decision deferred).
            - "stage-adopted": adopted interactively from staging via `adopt-staged`.
            - "stage-adopted-auto": adopted from staging via `adopt-staged --yes`
              (no human prompt; used by non-TTY coding-agent workflows).
            - "direct-remove": manual removal via `remove-skill` (interactive).
            - "direct-remove-auto": manual removal via `remove-skill --yes`.
        snapshot_path: Pivot snapshot directory written at run start (ADR-0020).
            ``None`` when the command did not produce a snapshot.
        reason: Human-provided justification for the action. Required for
            ``remove-skill`` and other manual CRUD; the field is always
            present in the record (null when omitted) for forward compat.
        source_ids: Lineage keys of the artifact's inputs (ADR-0050) —
            pattern content-hash ids for insight / distill-identity /
            amend-constitution, skill filenames for rules-distill. Always
            present in the record (null when the command has no lineage).
            Empty collections are deliberately normalized to null: every
            lineage-tracked command has ≥1 input by construction, so
            "tracked but empty" does not occur and null uniformly means
            "no lineage attached".
        epistemic_counts: Observed/generated tally of the artifact's input
            patterns (ADR-0050). Always present in the record (null when
            not applicable; empty dicts normalize to null, same rationale).
    """
    if approved is None:
        decision = "staged"
    elif approved:
        decision = "approved"
    else:
        decision = "rejected"
    record = {
        "ts": now_iso(timespec="seconds"),
        "command": command,
        "path": str(path),
        "decision": decision,
        "source": source,
        "content_hash": hashlib.sha256(content.encode()).hexdigest()[:16],
        "snapshot_path": str(snapshot_path) if snapshot_path is not None else None,
        "reason": reason,
        "source_ids": list(source_ids) if source_ids else None,
        "epistemic_counts": dict(epistemic_counts) if epistemic_counts else None,
    }
    try:
        append_jsonl_restricted(AUDIT_LOG_PATH, record)
    except OSError:
        logger.warning("Failed to write audit log: %s", AUDIT_LOG_PATH)


def _approve_write(path: Path) -> bool:
    """Prompt user for write approval. Default is N (safe side)."""
    print(f"\nWrite to {path}? [y/N] ", end="", flush=True)
    try:
        return input().strip().lower() == "y"
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def _approve_delete(path: Path) -> bool:
    """Prompt user for delete approval. Default is N (safe side)."""
    print(f"\nDelete {path}? [y/N] ", end="", flush=True)
    try:
        return input().strip().lower() == "y"
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def _run_approval_loop(
    items: Sequence[Any],
    *,
    command: str,
    target_dir: Path,
    snapshot_path: Optional[Path] = None,
) -> int:
    """Iterate generated artifacts through the approval gate, write approved.

    Each item must expose ``filename``, ``text``, and ``target_path``
    (``SkillResult`` / ``RuleResult`` from core/, and ``StageItem`` here
    all match this shape — kept structural to avoid dragging core types
    into the cli module signature).

    Per-handler post-loop hooks (``write_last_insight`` /
    ``_write_last_run``) and summary prints stay at the call site
    because the wording differs ("written" vs "revised", per-handler
    counters).

    Returns the count of approved+written items so the caller can
    decide whether to fire its post-loop hook.
    """
    from .core._io import write_restricted

    written = 0
    for i, item in enumerate(items, 1):
        print(f"\n{'='*60}")
        print(f"[{i}/{len(items)}] {item.filename}")
        print(item.text)
        approved = _approve_write(item.target_path)
        _log_approval(
            command,
            item.target_path,
            approved,
            item.text,
            snapshot_path=snapshot_path,
            # ADR-0050: SkillResult carries pattern_ids, RuleResult carries
            # source_ids (skill filenames); StageItem-shaped items carry
            # neither here (staging logs lineage itself).
            source_ids=(
                getattr(item, "pattern_ids", None)
                or getattr(item, "source_ids", None)
            ),
            epistemic_counts=getattr(item, "epistemic_counts", None),
        )
        if approved:
            target_dir.mkdir(parents=True, exist_ok=True)
            write_restricted(item.target_path, item.text)
            written += 1
        else:
            print("Skipped.")
    return written


def _is_dry_run(args: argparse.Namespace) -> bool:
    """Check if --dry-run was passed."""
    return getattr(args, "dry_run", False)


@dataclass(frozen=True)
class StageItem:
    """One artifact pending external approval in the staging dir.

    `sources` is only set by skill-stocktake merges: it lists original
    skill filenames that `adopt-staged` should delete when the merged
    result is accepted. All other commands leave it empty.

    `action` distinguishes merge (write) from drop (delete) operations.

    `command` overrides the batch command name passed to `_stage_results`.
    Used by stocktake handlers to mix merge ("skill-stocktake") and drop
    ("skill-stocktake-drop") items in a single staging batch — needed
    because `_stage_results` wipes the staging dir on every call, so a
    second call would erase the first batch.

    `source_ids` / `epistemic_counts` are ADR-0050 lineage metadata,
    deliberately distinct from `sources` — `sources` has delete-on-adopt
    semantics, lineage is record-only and rides through meta.json into
    the adopt-time audit entry.
    """

    filename: str
    text: str
    target_path: Path
    sources: list[str] = field(default_factory=list)
    action: Literal["merge", "drop"] = "merge"
    command: str | None = None
    source_ids: list[str] = field(default_factory=list)
    epistemic_counts: dict[str, int] = field(default_factory=dict)


def _stage_results(items: list[StageItem], command: str) -> None:
    """Write generated results to the staging directory for external approval.

    Creates the staging dir, writes each file plus a sidecar `*.meta.json`,
    records a 'staged' entry in the audit log, and prints paths for the
    calling agent to read.
    """
    STAGED_DIR.mkdir(parents=True, exist_ok=True)
    for old_file in STAGED_DIR.iterdir():
        if old_file.is_file():
            old_file.unlink()
    staged_paths = []
    data_root = MOLTBOOK_DATA_DIR.resolve()
    for item in items:
        if not item.target_path.resolve().is_relative_to(data_root):
            print(
                f"Error: target path escapes MOLTBOOK_HOME: {item.target_path}",
                file=sys.stderr,
            )
            continue
        item_command = item.command or command
        staged_file = STAGED_DIR / item.filename
        staged_file.write_text(item.text + "\n", encoding="utf-8")
        meta: dict[str, object] = {
            "target": str(item.target_path),
            "command": item_command,
        }
        if item.sources:
            meta["sources"] = list(item.sources)
        if item.action != "merge":
            meta["action"] = item.action
        # ADR-0050: lineage rides through meta.json so adopt-staged can
        # attach it to the adopt-time audit entry.
        if item.source_ids:
            meta["source_ids"] = list(item.source_ids)
        if item.epistemic_counts:
            meta["epistemic_counts"] = dict(item.epistemic_counts)
        meta_file = STAGED_DIR / f"{item.filename}.meta.json"
        meta_file.write_text(json_mod.dumps(meta, indent=2) + "\n", encoding="utf-8")
        staged_paths.append((staged_file, item.target_path))
        _log_approval(
            item_command, item.target_path, None, item.text, source="stage",
            source_ids=item.source_ids or None,
            epistemic_counts=item.epistemic_counts or None,
        )

    print(f"Staged {len(staged_paths)} file(s) in {STAGED_DIR}/")
    for staged, target in staged_paths:
        print(f"  {staged} → {target}")


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


def _list_templates() -> list[str]:
    """Return sorted list of available template names."""
    templates_dir = DEFAULT_CONFIG_DIR / "templates"
    if not templates_dir.is_dir():
        return []
    return sorted(
        d.name for d in templates_dir.iterdir()
        if d.is_dir() and (d / "identity.md").exists()
    )


def _do_init(template_name: str = "contemplative") -> None:
    """Initialize runtime data files in MOLTBOOK_HOME."""
    import shutil

    def copy_or_create_dir(src: Path, dst: Path, label: str, provenance: str = "") -> None:
        if dst.exists():
            print(f"{label} already exists: {dst}")
        elif src.is_dir():
            shutil.copytree(src, dst)
            print(f"Copied {label.lower()}: {dst}{provenance}")
        else:
            dst.mkdir(parents=True, exist_ok=True)
            print(f"Created empty {label.lower()} dir: {dst}")

    templates_dir = DEFAULT_CONFIG_DIR / "templates"
    template_dir = templates_dir / template_name
    if not template_dir.is_dir():
        available = ", ".join(_list_templates())
        print(f"Unknown template: {template_name}", file=sys.stderr)
        print(f"Available templates: {available}", file=sys.stderr)
        sys.exit(1)

    MOLTBOOK_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Identity
    src_identity = template_dir / "identity.md"
    if IDENTITY_PATH.exists():
        print(f"Identity file already exists: {IDENTITY_PATH}")
    elif src_identity.exists():
        IDENTITY_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_identity, IDENTITY_PATH)
        os.chmod(IDENTITY_PATH, stat.S_IRUSR | stat.S_IWUSR)
        print(f"Created identity file: {IDENTITY_PATH} (from {template_name})")

    # Knowledge (always empty, not template-specific)
    if KNOWLEDGE_PATH.exists():
        print(f"Knowledge file already exists: {KNOWLEDGE_PATH}")
    else:
        KNOWLEDGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        KNOWLEDGE_PATH.write_text(json_mod.dumps([], ensure_ascii=False) + "\n", encoding="utf-8")
        os.chmod(KNOWLEDGE_PATH, stat.S_IRUSR | stat.S_IWUSR)
        print(f"Created knowledge file: {KNOWLEDGE_PATH}")

    # Copy directories from template (constitution, skills, rules)
    template_suffix = f" (from {template_name})"
    for src_dir, dst_dir, label in [
        (template_dir / "constitution", CONSTITUTION_DIR, "Constitution"),
        (template_dir / "skills", SKILLS_DIR, "Skills"),
        (template_dir / "rules", RULES_DIR, "Rules"),
    ]:
        copy_or_create_dir(src_dir, dst_dir, label, template_suffix)

    # Copy shared runtime dirs (not template-specific) so the user owns
    # every Markdown file the agent consults at runtime. Edits here
    # surface via git-diff against config/ and are captured in pivot
    # snapshots for replayability.
    for src_dir, dst_dir, label in [
        (DEFAULT_CONFIG_DIR / "prompts", PROMPTS_DIR, "Prompts"),
        (DEFAULT_CONFIG_DIR / "views", VIEWS_DIR, "Views"),
    ]:
        copy_or_create_dir(src_dir, dst_dir, label)


def _configure_llm_and_domain(args: argparse.Namespace) -> DomainConfig | None:
    """Load domain config, constitution, skills, and rules into LLM.

    Returns the domain_config (or None) for Agent construction.
    """
    domain_config: DomainConfig | None = None
    if args.domain_config is not None:
        reset_caches()
        domain_config = load_domain_config(args.domain_config)
        set_domain_config_cache(domain_config)

    if not args.no_axioms:
        clauses = load_constitution(args.constitution_dir or CONSTITUTION_DIR)
        if clauses:
            configure_llm(axiom_prompt=clauses)

    if SKILLS_DIR.is_dir():
        configure_llm(skills_dir=SKILLS_DIR)
    if RULES_DIR.is_dir():
        configure_llm(rules_dir=RULES_DIR)

    return domain_config


# --- Tier 1: No LLM needed ---


def _handle_install_schedule(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
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
        if args.weekly_analysis:
            if args.weekly_analysis_day < 0 or args.weekly_analysis_day > 6:
                parser.error("--weekly-analysis-day must be 0 (Sun) to 6 (Sat)")
            if args.weekly_analysis_hour < 0 or args.weekly_analysis_hour > 23:
                parser.error("--weekly-analysis-hour must be between 0 and 23")
            _do_install_weekly_analysis_schedule(
                weekday=args.weekly_analysis_day,
                hour=args.weekly_analysis_hour,
            )


def _handle_stocktake_result(
    args: argparse.Namespace,
    result,
    *,
    target_dir: Path,
    label: str,
    merge_prompt: str,
    command_prefix: str,
    fallback_title: str,
    clean_prompt: str | None = None,
) -> None:
    """Shared body for _handle_skill_stocktake and _handle_rules_stocktake.

    Both handlers diff only in:
      - target_dir       (SKILLS_DIR vs RULES_DIR)
      - label            ("Skill" vs "Rules")
      - merge_prompt     (skill vs rules merge prompt template)
      - command_prefix   ("skill-stocktake" vs "rules-stocktake")
      - fallback_title   ("merged-skill" vs "merged-rule")

    Drop items use `f"{command_prefix}-drop"` for audit/meta consistency.

    Self-delete guard: when the merged title slugifies to one of the source
    filenames, target_path collides with an original. The guard skips the
    matching name so we don't delete the file we just wrote. See commit
    542f0b2 for the bug history.

    Single staging batch for merge + drop: `_stage_results` wipes STAGED_DIR
    on every call, so calling it twice (once for merges, once for drops)
    would erase the first batch. Per-item `command` lets us mix
    "<prefix>" and "<prefix>-drop" in one batch.
    """
    from datetime import date

    from .core._io import write_restricted
    from .core.stocktake import (
        clean_skill_triggers,
        format_stocktake_report,
        is_clean_noop,
        is_merge_rejected,
        merge_group,
    )
    from .core.text_utils import (
        extract_title,
        slugify,
        split_frontmatter,
        synthesize_frontmatter,
    )

    print(format_stocktake_report(result, label))

    # With a clean_prompt (skills), the clean phase may rewrite singleton
    # triggers even when there is nothing to merge or drop, so don't short-
    # circuit. Rules pass no clean_prompt and keep the original early return.
    if not result.merge_groups and not result.quality_issues and clean_prompt is None:
        return

    items_dict = dict(result.items)
    stage = getattr(args, "stage", False)
    drop_command = f"{command_prefix}-drop"

    # Filenames consumed by a successful merge (their originals get deleted on
    # adopt) and filenames flagged for drop. The clean phase skips both so it
    # only rewrites surviving singletons: merged skills are already cleaned by
    # the merge prompt, and dropped files don't need cleaning.
    consumed_names: set[str] = set()
    dropped_names = {issue.filename for issue in result.quality_issues}

    staged_batch: list[StageItem] = []

    # --- Merge duplicates ---
    merged = 0
    if result.merge_groups:
        print(f"\n{'='*60}")
        print(f"Merging {len(result.merge_groups)} group(s)...")

        for i, group in enumerate(result.merge_groups, 1):
            group_items = [
                (name, items_dict[name])
                for name in group.filenames
                if name in items_dict
            ]
            if len(group_items) < 2:
                continue

            print(f"\n{'='*60}")
            print(f"[Group {i}/{len(result.merge_groups)}] {', '.join(group.filenames)}")
            print(f"  Reason: {group.reason}")

            merged_text = merge_group(group_items, merge_prompt)
            if merged_text is None:
                print("  Merge failed (LLM error). Skipping.")
                continue

            if is_merge_rejected(merged_text):
                print(f"  LLM rejected merge: {merged_text.strip()}")
                print("  Skipping (candidates judged not actually redundant).")
                continue

            print(merged_text)

            title = extract_title(merged_text) or fallback_title
            slug = slugify(title) or fallback_title
            filename = f"{slug}-{date.today().strftime('%Y%m%d')}.md"
            target_path = target_dir / filename

            if stage:
                # Record original filenames so adopt-staged can delete them on approval.
                staged_batch.append(
                    StageItem(
                        filename=filename,
                        text=merged_text,
                        target_path=target_path,
                        sources=list(group.filenames),
                    )
                )
                consumed_names.update(group.filenames)
                continue

            approved = _approve_write(target_path)
            _log_approval(command_prefix, target_path, approved, merged_text)
            if approved:
                target_dir.mkdir(parents=True, exist_ok=True)
                write_restricted(target_path, merged_text)
                try:
                    target_resolved = target_path.resolve()
                except OSError:
                    target_resolved = target_path
                for name in group.filenames:
                    original = target_dir / name
                    try:
                        same_as_target = original.resolve() == target_resolved
                    except OSError:
                        same_as_target = original == target_path
                    if same_as_target:
                        continue
                    if original.exists():
                        original.unlink()
                        print(f"  Deleted {name}")
                merged += 1
                consumed_names.update(group.filenames)
            else:
                print("  Skipped.")

        if not stage:
            print(f"\n--- Merge summary: {merged} merged, {len(result.merge_groups) - merged} skipped ---")

    # --- Drop low-quality files ---
    if result.quality_issues:
        print(f"\n{'='*60}")
        print(f"Low-quality files: {len(result.quality_issues)}")

        dropped = 0
        for issue in result.quality_issues:
            target_path = target_dir / issue.filename
            if not target_path.exists():
                continue
            body = items_dict.get(issue.filename, "")
            if not body:
                # Defensive: quality_issues and items both come from
                # _read_files, so they should agree. Skip rather than
                # stage an empty artifact if they ever drift.
                print(f"  Skipped (empty body): {issue.filename}")
                continue

            print(f"\n{'='*60}")
            print(f"[Drop candidate] {issue.filename}")
            print(f"  Reason: {issue.reason}")
            print(body[:500])

            if stage:
                staged_batch.append(
                    StageItem(
                        filename=issue.filename,
                        text=body,
                        target_path=target_path,
                        action="drop",
                        command=drop_command,
                    )
                )
                continue

            approved = _approve_delete(target_path)
            _log_approval(drop_command, target_path, approved, body)
            if approved:
                target_path.unlink()
                print(f"  Deleted {issue.filename}")
                dropped += 1
            else:
                print("  Kept.")

        if not stage:
            print(f"\n--- Drop summary: {dropped} deleted, {len(result.quality_issues) - dropped} kept ---")

    # --- Clean singleton triggers (skills only) ---
    # A merged skill is rewritten at structural altitude by the merge prompt,
    # but a skill with no twin never goes through a merge and keeps its
    # original episode-derived triggers (proper nouns, timestamp windows, the
    # saturated relevance score). This pass cleans those survivors so every
    # surviving skill ends up with reusable triggers. Files consumed by a
    # merge or flagged for drop are excluded; CLEAN_NOOP keeps it idempotent.
    if clean_prompt is not None:
        clean_command = f"{command_prefix}-clean"
        clean_targets = [
            (name, body)
            for name, body in result.items
            if name not in consumed_names and name not in dropped_names
        ]
        if clean_targets:
            print(f"\n{'='*60}")
            print(f"Cleaning triggers for {len(clean_targets)} skill(s)...")

        cleaned = 0
        for name, body in clean_targets:
            cleaned_text = clean_skill_triggers((name, body), clean_prompt)
            if cleaned_text is None:
                print(f"  Clean failed (LLM error): {name}")
                continue
            if is_clean_noop(cleaned_text):
                continue  # triggers already at structural altitude

            target_path = target_dir / name

            # The cleaned body comes from a frontmatter-stripped source
            # (result.items strips it), so re-attach the skill's original
            # frontmatter — name / description / origin and any reflection
            # bookkeeping — before writing. Without this, a cleaned singleton
            # would silently lose its metadata. Legacy skills that predate
            # frontmatter emission get a synthesized block instead.
            try:
                original = target_path.read_text(encoding="utf-8")
            except OSError:
                original = ""
            _, cleaned_body = split_frontmatter(cleaned_text)
            # split_frontmatter only lstrips the body when it consumed a
            # frontmatter block; for the common frontmatter-less clean output
            # a stray leading newline from the model would yield a triple-blank
            # gap under the re-attached frontmatter, so strip it here.
            cleaned_body = cleaned_body.lstrip("\n")
            frontmatter, _ = split_frontmatter(original)
            if not frontmatter:
                frontmatter = synthesize_frontmatter(cleaned_body)
            final_text = f"{frontmatter}\n\n{cleaned_body}"

            print(f"\n{'='*60}")
            print(f"[Clean] {name}")
            print(final_text)

            if stage:
                staged_batch.append(
                    StageItem(
                        filename=name,
                        text=final_text,
                        target_path=target_path,
                        command=clean_command,
                    )
                )
                continue

            approved = _approve_write(target_path)
            _log_approval(clean_command, target_path, approved, final_text)
            if approved:
                write_restricted(target_path, final_text)
                cleaned += 1
                print(f"  Cleaned {name}")
            else:
                print("  Skipped.")

        if not stage and clean_targets:
            print(
                f"\n--- Clean summary: {cleaned} cleaned, "
                f"{len(clean_targets) - cleaned} unchanged/skipped ---"
            )

    if stage and staged_batch:
        _stage_results(staged_batch, command=command_prefix)


def _handle_skill_stocktake(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    """Audit skills and merge duplicates / drop low-quality files."""
    from .core import prompts
    from .core.stocktake import run_skill_stocktake

    result = run_skill_stocktake(skills_dir=SKILLS_DIR)
    _handle_stocktake_result(
        args,
        result,
        target_dir=SKILLS_DIR,
        label="Skill",
        merge_prompt=prompts.STOCKTAKE_MERGE_PROMPT,
        command_prefix="skill-stocktake",
        fallback_title="merged-skill",
        clean_prompt=prompts.STOCKTAKE_CLEAN_PROMPT,
    )


def _handle_rules_stocktake(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    """Audit rules and merge duplicates / drop low-quality files.

    Uses STOCKTAKE_MERGE_RULES_PROMPT (Practice/Rationale structure) instead
    of the skill-oriented STOCKTAKE_MERGE_PROMPT. All other behavior is
    shared via `_handle_stocktake_result`.
    """
    from .core import prompts
    from .core.stocktake import run_rules_stocktake

    result = run_rules_stocktake(rules_dir=RULES_DIR)
    _handle_stocktake_result(
        args,
        result,
        target_dir=RULES_DIR,
        label="Rules",
        merge_prompt=prompts.STOCKTAKE_MERGE_RULES_PROMPT,
        command_prefix="rules-stocktake",
        fallback_title="merged-rule",
    )


def _handle_sync_data(_args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    _run_sync()


def _handle_adopt_staged(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    """Walk the staging dir, run each staged file through the approval gate,
    and write accepted files to their target paths. Rejected and accepted
    items are both removed from staging to avoid repeated prompts on rerun.

    With ``--yes`` (``args.yes == True``) the interactive prompts are
    skipped and every staged item is auto-approved. This is the path that
    coding agents (Claude Code, etc.) use because their bash sandbox is
    non-TTY: ``input()`` would otherwise return EOF and reject everything.
    Auto-approved entries are recorded in the audit log with
    ``source="stage-adopted-auto"`` so they can be distinguished from
    interactively reviewed adoptions.
    """
    from .core._io import write_restricted

    yes = getattr(args, "yes", False)
    audit_source: AuditSource = "stage-adopted-auto" if yes else "stage-adopted"

    if not STAGED_DIR.exists():
        print("No staging directory.")
        return

    meta_files = sorted(STAGED_DIR.glob("*.meta.json"))
    if not meta_files:
        print("No staged files.")
        return

    if yes:
        print(f"Auto-approve mode (--yes): adopting {len(meta_files)} staged item(s) without prompts.")

    adopted = 0
    rejected = 0
    skipped = 0
    data_root = MOLTBOOK_DATA_DIR.resolve()
    for meta_file in meta_files:
        try:
            meta = json_mod.loads(meta_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as err:
            print(f"  Skipped (meta read error): {meta_file.name}: {err}")
            skipped += 1
            continue

        target_str = meta.get("target")
        command = meta.get("command")
        sources = meta.get("sources") or []
        action = meta.get("action", "merge")
        # ADR-0050: lineage staged alongside the artifact; attach it to
        # the adopt-time audit entry so deferred approval keeps lineage.
        staged_source_ids = meta.get("source_ids") or None
        staged_epistemic_counts = meta.get("epistemic_counts") or None
        if not target_str or not command:
            print(f"  Skipped (invalid meta): {meta_file.name}")
            skipped += 1
            continue

        target = Path(target_str)
        # Defense in depth: the meta.json is user-writable between stage and
        # adopt, so re-verify the target still lives inside MOLTBOOK_HOME.
        try:
            inside = target.resolve().is_relative_to(data_root)
        except OSError:
            inside = False
        if not inside:
            print(
                f"Error: staged target escapes MOLTBOOK_HOME: {target}",
                file=sys.stderr,
            )
            skipped += 1
            continue

        content_file = meta_file.parent / meta_file.name[: -len(".meta.json")]
        if not content_file.exists():
            print(f"  Skipped (content missing): {content_file.name}")
            skipped += 1
            continue

        try:
            text = content_file.read_text(encoding="utf-8")
        except OSError as err:
            print(f"  Skipped (content read error): {content_file.name}: {err}")
            skipped += 1
            continue

        print(f"\n{'='*60}")
        print(f"[{command}] {content_file.name} -> {target}")
        print(text)

        if action == "drop":
            approved = True if yes else _approve_delete(target)
            _log_approval(
                command, target, approved, text, source=audit_source,
                source_ids=staged_source_ids,
                epistemic_counts=staged_epistemic_counts,
            )
            if approved:
                if target.exists():
                    target.unlink()
                    print(f"  Deleted {target.name}")
                else:
                    print(f"  Already absent: {target.name}")
                adopted += 1
            else:
                print("  Kept.")
                rejected += 1
        else:
            approved = True if yes else _approve_write(target)
            _log_approval(
                command, target, approved, text, source=audit_source,
                source_ids=staged_source_ids,
                epistemic_counts=staged_epistemic_counts,
            )
            if approved:
                target.parent.mkdir(parents=True, exist_ok=True)
                to_write = text if text.endswith("\n") else text + "\n"
                write_restricted(target, to_write)
                # skill-stocktake merges pass the original filenames in `sources`
                # so they get deleted once the merged result is adopted.
                target_parent = target.parent.resolve()
                try:
                    target_resolved = target.resolve()
                except OSError:
                    target_resolved = target
                for src_name in sources:
                    src_path = (target.parent / src_name).resolve()
                    try:
                        same_dir = src_path.parent == target_parent
                    except OSError:
                        same_dir = False
                    if not same_dir:
                        print(
                            f"  Skipped source delete (outside target dir): {src_name}"
                        )
                        continue
                    # Guard: when the merged title collides with an original
                    # filename, src_path == target. Skip so we don't delete
                    # the file we just wrote.
                    if src_path == target_resolved:
                        continue
                    if src_path.exists():
                        src_path.unlink()
                        print(f"  Deleted {src_name}")
                adopted += 1
            else:
                print("Skipped.")
                rejected += 1

        content_file.unlink(missing_ok=True)
        meta_file.unlink(missing_ok=True)

    print(
        f"\n--- Summary: {adopted} adopted, {rejected} rejected, "
        f"{skipped} skipped ---"
    )


def _handle_remove_skill(
    args: argparse.Namespace, _parser: argparse.ArgumentParser
) -> None:
    """Delete a skill from ``skills_dir`` with an audit trail.

    The single manual-CRUD entry point for the skills directory. Writes an
    ``audit.jsonl`` record (command="remove-skill") capturing the reason,
    decision, and content hash so the deletion is reviewable alongside the
    automated approval-gate history (ADR-0012).

    With ``--yes`` the interactive prompt is skipped (non-TTY workflows).
    With ``--dry-run`` the target is resolved and printed but nothing is
    written or removed.
    """
    reason = (args.reason or "").strip()
    if not reason:
        print(
            "Error: --reason is required and must be non-empty.",
            file=sys.stderr,
        )
        sys.exit(2)

    skills_dir = (MOLTBOOK_DATA_DIR / "skills").resolve()
    name = args.name
    if not name.endswith(".md"):
        name = f"{name}.md"
    target = (skills_dir / name).resolve()

    try:
        inside = target.is_relative_to(skills_dir)
    except (OSError, ValueError):
        inside = False
    if not inside:
        print(
            f"Error: target escapes skills dir: {target}",
            file=sys.stderr,
        )
        sys.exit(2)

    if not target.is_file():
        print(f"Error: skill not found: {target}", file=sys.stderr)
        sys.exit(1)

    if getattr(args, "dry_run", False):
        print(f"[dry-run] would remove: {target}")
        print(f"[dry-run] reason: {reason}")
        return

    try:
        text = target.read_text(encoding="utf-8")
    except OSError as err:
        print(f"Error: cannot read {target}: {err}", file=sys.stderr)
        sys.exit(1)

    yes = getattr(args, "yes", False)
    source: AuditSource = "direct-remove-auto" if yes else "direct-remove"
    approved = True if yes else _approve_delete(target)

    _log_approval(
        command="remove-skill",
        path=target,
        approved=approved,
        content=text,
        source=source,
        reason=reason,
    )

    if approved:
        target.unlink()
        print(f"Removed {target.name}")
    else:
        print("Kept.")


# --- Tier 2: LLM config needed ---


def _handle_init(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    _do_init(template_name=args.template)


def _handle_distill(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
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
    # Blocking lock (audit M5): wait for an active run session to finish
    # rather than skip — a skipped daily distill loses its --days window
    # (the next scheduled run reads a later window). Manual commands
    # (meditate / dialogue / insight) are deliberately NOT lock-gated:
    # they are operator-driven and making them queue behind a scheduled
    # session would be surprising.
    logger.info("Acquiring run lock (waits if a session is active)")
    with acquire_run_lock(RUN_LOCK_PATH, blocking=True):
        episode_log = EpisodeLog(log_dir=log_dir)
        knowledge_store = KnowledgeStore(path=KNOWLEDGE_PATH)
        view_registry = _load_view_registry(args)
        knowledge_store.load()
        _take_snapshot(args, "distill", view_registry)
        result = distill(
            days=args.days,
            dry_run=args.dry_run,
            episode_log=episode_log,
            knowledge_store=knowledge_store,
            log_files=log_files,
            view_registry=view_registry,
            log_dir=log_dir,
        )
        print(result)


def _resolve_views_dir() -> Path:
    """Prefer the user-customised VIEWS_DIR, fall back to packaged template."""
    if VIEWS_DIR.exists():
        return VIEWS_DIR
    repo_root = Path(__file__).resolve().parents[2]
    packaged = repo_root / "config" / "views"
    if packaged.exists():
        return packaged
    return VIEWS_DIR


def _load_view_registry(
    args: Optional[argparse.Namespace] = None,
) -> "ViewRegistry":
    """Load the view registry, preferring user-customised views.

    Passes ``${CONSTITUTION_DIR}`` to seed_from resolution so views can
    inject live constitution content (honours ``--constitution-dir``).
    """
    from .core.views import ViewRegistry

    constitution_dir = (
        getattr(args, "constitution_dir", None) if args is not None else None
    ) or CONSTITUTION_DIR
    registry = ViewRegistry(
        views_dir=_resolve_views_dir(),
        path_vars={"CONSTITUTION_DIR": constitution_dir},
    )
    registry.load_views()
    return registry


def _take_snapshot(
    args: argparse.Namespace,
    command: str,
    view_registry: Optional["ViewRegistry"] = None,
) -> Optional[Path]:
    """Write a pivot snapshot at the start of a behavior-producing command.

    Skipped when the caller passes ``--dry-run`` (only ``distill`` still
    accepts that flag after ADR-0035; the other approval-gated callers
    rely on the approval prompt to discard). Returns None if
    snapshotting fails — callers must not treat a missing snapshot as
    an error (ADR-0020: snapshots are observability, not correctness).
    """
    if _is_dry_run(args):
        return None
    from .core.snapshot import SnapshotCommand, write_snapshot

    return write_snapshot(
        command=cast(SnapshotCommand, command),
        views_dir=_resolve_views_dir(),
        constitution_dir=getattr(args, "constitution_dir", None) or CONSTITUTION_DIR,
        snapshots_dir=SNAPSHOTS_DIR,
        prompts_dir=PROMPTS_DIR if PROMPTS_DIR.is_dir() else None,
        skills_dir=SKILLS_DIR if SKILLS_DIR.is_dir() else None,
        rules_dir=RULES_DIR if RULES_DIR.is_dir() else None,
        identity_path=IDENTITY_PATH if IDENTITY_PATH.is_file() else None,
        view_registry=view_registry,
    )


def _handle_enrich(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    from .core.distill import enrich
    from .core.memory import KnowledgeStore

    knowledge_store = KnowledgeStore(path=KNOWLEDGE_PATH)
    knowledge_store.load()

    sub_count = enrich(knowledge_store, dry_run=args.dry_run)
    print(f"Subcategorized: {sub_count}")


def _handle_distill_identity(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    from .core.distill import distill_identity
    from .core.memory import KnowledgeStore

    knowledge_store = KnowledgeStore(path=KNOWLEDGE_PATH)
    view_registry = _load_view_registry(args)
    knowledge_store.load()
    snapshot_path = _take_snapshot(args, "distill-identity", view_registry)
    result = distill_identity(
        knowledge_store=knowledge_store,
        identity_path=IDENTITY_PATH,
        view_registry=view_registry,
    )
    if isinstance(result, str):
        print(result)
        return
    print(result.text)
    if getattr(args, "stage", False):
        _stage_results(
            [StageItem(
                "identity.md", result.text, result.target_path,
                source_ids=list(result.pattern_ids),
                epistemic_counts=dict(result.epistemic_counts),
            )],
            command="distill-identity",
        )
        return
    approved = _approve_write(result.target_path)
    _log_approval(
        "distill-identity", result.target_path, approved, result.text,
        snapshot_path=snapshot_path,
        source_ids=result.pattern_ids,
        epistemic_counts=result.epistemic_counts,
    )
    if not approved:
        print("Discarded.")
        return
    from .core._io import write_restricted as _wr
    _wr(result.target_path, result.text + "\n")


def _handle_insight(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    from .core.insight import extract_insight, write_last_insight
    from .core.memory import KnowledgeStore

    knowledge_store = KnowledgeStore(path=KNOWLEDGE_PATH)
    view_registry = _load_view_registry(args)
    knowledge_store.load()
    snapshot_path = _take_snapshot(args, "insight", view_registry)
    result = extract_insight(
        knowledge_store=knowledge_store,
        skills_dir=SKILLS_DIR,
        full=args.full,
    )
    if isinstance(result, str):
        print(result)
        return
    if getattr(args, "stage", False):
        _stage_results(
            [StageItem(
                s.filename, s.text, s.target_path,
                source_ids=list(s.pattern_ids),
                epistemic_counts=dict(s.epistemic_counts),
            ) for s in result.skills],
            command="insight",
        )
        return
    written = _run_approval_loop(
        result.skills,
        command="insight",
        target_dir=SKILLS_DIR,
        snapshot_path=snapshot_path,
    )
    if written > 0:
        write_last_insight(SKILLS_DIR)
    print(f"\n--- Summary: {written} written, {len(result.skills) - written} skipped, {result.dropped_count} dropped ---")


def _handle_rules_distill(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    from .core.rules_distill import _write_last_run, distill_rules

    snapshot_path = _take_snapshot(args, "rules-distill", _load_view_registry(args))
    result = distill_rules(
        skills_dir=SKILLS_DIR,
        rules_dir=RULES_DIR,
        full=args.full,
    )
    if isinstance(result, str):
        print(result)
        return
    if getattr(args, "stage", False):
        _stage_results(
            [StageItem(
                r.filename, r.text, r.target_path,
                source_ids=list(r.source_ids),
            ) for r in result.rules],
            command="rules-distill",
        )
        return
    written = _run_approval_loop(
        result.rules,
        command="rules-distill",
        target_dir=RULES_DIR,
        snapshot_path=snapshot_path,
    )
    if written > 0:
        _write_last_run(RULES_DIR)
    print(f"\n--- Summary: {written} written, {len(result.rules) - written} skipped, {result.dropped_count} dropped ---")


def _handle_amend_constitution(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    from .core.constitution import amend_constitution
    from .core.memory import KnowledgeStore

    knowledge_store = KnowledgeStore(path=KNOWLEDGE_PATH)
    constitution_dir = args.constitution_dir or CONSTITUTION_DIR
    view_registry = _load_view_registry(args)
    snapshot_path = _take_snapshot(args, "amend-constitution")
    result = amend_constitution(
        knowledge_store=knowledge_store,
        constitution_dir=constitution_dir,
        view_registry=view_registry,
    )
    if isinstance(result, str):
        print(result)
        return
    print(result.text)
    if getattr(args, "stage", False):
        _stage_results(
            [StageItem(
                result.target_path.name, result.text, result.target_path,
                source_ids=list(result.pattern_ids),
                epistemic_counts=dict(result.epistemic_counts),
            )],
            command="amend-constitution",
        )
        return
    approved = _approve_write(result.target_path)
    _log_approval(
        "amend-constitution", result.target_path, approved, result.text,
        snapshot_path=snapshot_path,
        source_ids=result.pattern_ids,
        epistemic_counts=result.epistemic_counts,
    )
    if not approved:
        print("Discarded.")
        return
    from .core._io import write_restricted as _wr
    _wr(result.target_path, result.text + "\n")
    marker = result.marker_dir / ".last_constitution_amend"
    marker.write_text(now_iso() + "\n", encoding="utf-8")


def _handle_report(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    from .core.memory import EpisodeLog
    from .core.metrics import compute_metrics, format_report

    log_dir = MOLTBOOK_DATA_DIR / "logs"
    episode_log = EpisodeLog(log_dir=log_dir)
    report = compute_metrics(episode_log, days=args.days)
    print(format_report(report, fmt=args.format))


def _handle_generate_report(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
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


def _handle_meditate(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
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


_PRODUCTION_HOME = DEFAULT_MOLTBOOK_HOME.resolve()
_SHUTDOWN_GRACE_SECONDS = 5


def _exit_with(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)


def _spawn_dialogue_peer(
    *,
    home: Path,
    turns: int,
    stdin_fd: int,
    stdout_fd: int,
    seed: Optional[str] = None,
) -> subprocess.Popen:
    # CONTEMPLATIVE_DIALOGUE_PEER_MODULE lets an outer wrapper (e.g. a
    # managed-LLM shim) route peers through its own entry module so the
    # wrapper's setup (like a configured LLM backend) runs in each peer
    # process too. Default keeps the built-in path unchanged.
    peer_module = os.environ.get(
        "CONTEMPLATIVE_DIALOGUE_PEER_MODULE",
        "contemplative_agent.cli",
    )
    cmd = [
        sys.executable, "-u", "-m", peer_module,
        "dialogue-peer", "--turns", str(turns), "--label", home.name,
    ]
    if seed is not None:
        cmd += ["--seed", seed]
    env = {**os.environ, "MOLTBOOK_HOME": str(home)}
    return subprocess.Popen(
        cmd, stdin=stdin_fd, stdout=stdout_fd, env=env, close_fds=True,
    )


def _stop_peer(proc: subprocess.Popen) -> int:
    """Terminate a peer gracefully; escalate to SIGKILL if it ignores SIGTERM."""
    proc.terminate()
    try:
        return proc.wait(timeout=_SHUTDOWN_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        proc.kill()
        return proc.wait()


def _handle_dialogue(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    """Spawn two peer subprocesses with bidirectional pipes and wait for them.

    Each peer inherits a distinct MOLTBOOK_HOME so their episode logs stay
    separate — production (~/.config/moltbook) is never touched.
    """
    if args.turns < 1:
        _exit_with("--turns must be >= 1")
    if not args.seed.strip():
        _exit_with("--seed must be a non-empty string")

    home_a = args.home_a.expanduser().resolve()
    home_b = args.home_b.expanduser().resolve()
    for home, label in [(home_a, "HOME_A"), (home_b, "HOME_B")]:
        if home == _PRODUCTION_HOME or _PRODUCTION_HOME in home.parents:
            _exit_with(
                f"{label} ({home}) overlaps with production (~/.config/moltbook); "
                "pick a different MOLTBOOK_HOME for the dialogue sandbox."
            )
        if not home.is_dir():
            _exit_with(
                f"{label} ({home}) does not exist — initialise first with "
                f"'MOLTBOOK_HOME={home} contemplative-agent init'"
            )
        if not (home / "identity.md").is_file():
            _exit_with(
                f"{label} ({home}) has no identity.md — initialise with "
                f"'MOLTBOOK_HOME={home} contemplative-agent init'"
            )

    a_to_b_r, a_to_b_w = os.pipe()
    b_to_a_r, b_to_a_w = os.pipe()

    proc_a = _spawn_dialogue_peer(
        home=home_a, turns=args.turns,
        stdin_fd=b_to_a_r, stdout_fd=a_to_b_w, seed=args.seed,
    )
    proc_b = _spawn_dialogue_peer(
        home=home_b, turns=args.turns,
        stdin_fd=a_to_b_r, stdout_fd=b_to_a_w, seed=None,
    )
    # Parent releases its pipe ends so EOF propagates when a peer exits.
    for fd in (a_to_b_r, a_to_b_w, b_to_a_r, b_to_a_w):
        os.close(fd)

    try:
        rc_a = proc_a.wait()
        rc_b = proc_b.wait()
    except KeyboardInterrupt:
        rc_a = _stop_peer(proc_a)
        rc_b = _stop_peer(proc_b)

    if rc_a != 0 or rc_b != 0:
        logger.warning("dialogue peers exited with codes a=%d b=%d", rc_a, rc_b)
        sys.exit(1)


def _handle_dialogue_peer(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    """Run one peer's dialogue loop against stdin/stdout.

    LLM and domain are already configured by ``_configure_llm_and_domain``
    (tier-2 dispatch). This handler only has to wire an EpisodeLog rooted at
    the current MOLTBOOK_HOME and drive the loop.
    """
    from .adapters.dialogue.peer import run_peer_loop
    from .core.episode_log import EpisodeLog

    episode_log = EpisodeLog(log_dir=EPISODE_LOG_DIR)
    run_peer_loop(
        episode_log=episode_log,
        peer_in=sys.stdin,
        peer_out=sys.stdout,
        max_turns=args.turns,
        seed=args.seed,
        label=args.label,
    )


# --- Tier 3: Agent instance needed ---


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
        session_meta = {
            "axioms_enabled": not args.no_axioms,
            "domain": dc.name,
            "ollama_model": os.environ.get("OLLAMA_MODEL", "qwen3.5:9b"),
        }
        # Non-blocking lock (audit M5): a second concurrent session would
        # double-spend rate budgets and race knowledge.json — fail fast
        # with a clear message instead of queueing behind it.
        with acquire_run_lock(RUN_LOCK_PATH, blocking=False) as acquired:
            if not acquired:
                print(
                    "Another run/distill process holds the run lock "
                    f"({RUN_LOCK_PATH}); exiting."
                )
                return
            agent.run_session(
                duration_minutes=args.session, session_meta=session_meta
            )
    elif args.command == "solve":
        agent.do_solve(args.text)


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
    init_parser = subparsers.add_parser("init", help="Initialize identity and knowledge files")
    init_parser.add_argument(
        "--template", type=str, default="contemplative",
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
        "--file", type=Path, nargs="+", dest="log_files",
        help="Explicit JSONL log file(s) to process (overrides --days)"
    )

    # distill-identity
    distill_id_parser = subparsers.add_parser(
        "distill-identity", help="Distill knowledge into identity (without pattern distillation)"
    )
    distill_id_parser.add_argument(
        "--stage", action="store_true", help="Write to staging dir instead of interactive approval (for coding agents)"
    )

    # rules-distill
    rules_distill_parser = subparsers.add_parser(
        "rules-distill", help="Distill universal behavioral rules from skill files"
    )
    rules_distill_parser.add_argument(
        "--full", action="store_true", help="Process all patterns (not just new ones)"
    )
    rules_distill_parser.add_argument(
        "--stage", action="store_true", help="Write to staging dir instead of interactive approval (for coding agents)"
    )

    # amend-constitution
    amend_parser = subparsers.add_parser(
        "amend-constitution", help="Propose amendments to the constitution from accumulated ethical experience"
    )
    amend_parser.add_argument(
        "--stage", action="store_true", help="Write to staging dir instead of interactive approval (for coding agents)"
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
        "--session", type=int, default=60,
        help="Session duration in minutes (default: 60)",
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
    schedule_parser.add_argument(
        "--weekly-analysis", action="store_true",
        help="Also install weekly analysis report schedule",
    )
    schedule_parser.add_argument(
        "--weekly-analysis-day", type=int, default=1,
        help="Day of week for weekly analysis (0=Sun..6=Sat, default: 1=Mon)",
    )
    schedule_parser.add_argument(
        "--weekly-analysis-hour", type=int, default=9,
        help="Hour to run weekly analysis (0-23, default: 9)",
    )

    # insight
    insight_parser = subparsers.add_parser(
        "insight", help="Extract behavioral skill from accumulated knowledge"
    )
    insight_parser.add_argument(
        "--full", action="store_true", help="Process all patterns (default: new only)"
    )
    insight_parser.add_argument(
        "--stage", action="store_true", help="Write to staging dir instead of interactive approval (for coding agents)"
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

    # dialogue — spawn two peer agents (each rooted at a different MOLTBOOK_HOME)
    # and pipe them together for a local turn-based conversation.
    dialogue_parser = subparsers.add_parser(
        "dialogue",
        help="Run a local dialogue between two agent instances (two MOLTBOOK_HOMEs)",
    )
    dialogue_parser.add_argument(
        "home_a", type=Path,
        help="MOLTBOOK_HOME for agent A (initiator). Must be pre-initialised.",
    )
    dialogue_parser.add_argument(
        "home_b", type=Path,
        help="MOLTBOOK_HOME for agent B (responder). Must be pre-initialised.",
    )
    dialogue_parser.add_argument(
        "--seed", type=str, required=True,
        help="Opening message from agent A that starts the dialogue",
    )
    dialogue_parser.add_argument(
        "--turns", type=int, default=5,
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
        "--turns", type=int, required=True,
        help="Max reply turns this peer will generate",
    )
    dialogue_peer_parser.add_argument(
        "--seed", type=str, default=None,
        help="Opening message if this peer is the initiator",
    )
    dialogue_peer_parser.add_argument(
        "--label", type=str, default="peer",
        help="Short label for stderr traces",
    )

    # skill-stocktake
    skill_stocktake_parser = subparsers.add_parser("skill-stocktake", help="Audit skills for duplicates and quality issues")
    skill_stocktake_parser.add_argument(
        "--stage", action="store_true", help="Write merged skills to staging dir instead of interactive approval"
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
        "enrich", help="Enrich existing patterns with subcategories"
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
    solve_parser = subparsers.add_parser(
        "solve", help="Test verification solver"
    )
    solve_parser.add_argument("text", help="Obfuscated challenge text")

    args = parser.parse_args()
    _setup_logging(args.verbose)

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # Tier 1: Commands that don't need LLM or domain config
    no_llm_handlers: dict[str, Callable[..., None]] = {
        "install-schedule": _handle_install_schedule,
        "skill-stocktake": _handle_skill_stocktake,
        "rules-stocktake": _handle_rules_stocktake,
        "sync-data": _handle_sync_data,
        "adopt-staged": _handle_adopt_staged,
        "remove-skill": _handle_remove_skill,
        "dialogue": _handle_dialogue,
    }
    handler = no_llm_handlers.get(args.command)
    if handler:
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


if __name__ == "__main__":
    main()
