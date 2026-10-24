"""``restore-skill``: move one skill back from ``skills/.archive/`` (ADR-0122).

The human's right of return for the skill store's exit. Archiving never
deletes (ADR-0097 D5), so a restore is a move in the opposite direction plus an
audit row -- ``direct-restore`` -- which is what lets the layer-1 guard count
"archived by the unattended rule, then restored within four weeks"
(``scripts/layer1_exit_guard.py``). A bare ``mv`` works too but leaves no row,
so the guard would never see it; this command is the counted path.

Refusals are reason-coded and each writes a ``rejected`` row (ADR-0075), the
same rule ``_record_archive`` follows. Nothing is overwritten: a live skill of
the same name makes the restore refuse rather than choose.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from ..adapters.moltbook import config
from . import approval
from .registry import CommandSpec, Tier
from .store_paths import _skills_dir

logger = logging.getLogger(__name__)

_RESTORE_REFUSED_NOT_ARCHIVED = "RESTORE_REFUSED_NOT_ARCHIVED"
_RESTORE_REFUSED_SYMLINK = "RESTORE_REFUSED_SYMLINK"
_RESTORE_REFUSED_OUTSIDE = "RESTORE_REFUSED_OUTSIDE"
_RESTORE_REFUSED_LIVE_EXISTS = "RESTORE_REFUSED_LIVE_EXISTS"
_RESTORE_REFUSED_UNREADABLE = "RESTORE_REFUSED_UNREADABLE"
_RESTORE_WRITE_FAILED = "RESTORE_WRITE_FAILED"
_RESTORE_UNRECORDED = "RESTORE_UNRECORDED"


def _refuse(code: str, detail: str, *, command: str, path: Path, reason: str) -> None:
    """Print, write the ``rejected`` row, exit 1."""
    print(f"Error: {code}: {detail}", file=sys.stderr)
    approval._log_decision(
        "rejected",
        command,
        path,
        "",
        source="direct-restore",
        snapshot_path=None,
        reason=f"{reason} [{code}]",
        source_ids=None,
        epistemic_counts=None,
    )
    sys.exit(1)


def _handle_restore_skill(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    reason = (args.reason or "").strip()
    if not reason:
        print("Error: --reason is required and must be non-empty.", file=sys.stderr)
        sys.exit(2)

    data_root = config.MOLTBOOK_DATA_DIR.resolve()
    skills_dir = _skills_dir(data_root).resolve()
    archive_dir = skills_dir / ".archive"

    name = args.name if args.name.endswith(".md") else f"{args.name}.md"
    if "/" in name or "\\" in name or name.startswith("."):
        print(
            f"Error: {_RESTORE_REFUSED_OUTSIDE}: {name!r} is not a bare skill name", file=sys.stderr
        )
        sys.exit(2)
    source = archive_dir / name
    live = skills_dir / name
    command = "restore-skill"

    if source.is_symlink():
        _refuse(
            _RESTORE_REFUSED_SYMLINK,
            f"{name} in the archive is a symlink",
            command=command,
            path=source,
            reason=reason,
        )
    if not source.is_file():
        _refuse(
            _RESTORE_REFUSED_NOT_ARCHIVED,
            f"{name} is not in {archive_dir}",
            command=command,
            path=source,
            reason=reason,
        )
    if live.exists() or live.is_symlink():
        _refuse(
            _RESTORE_REFUSED_LIVE_EXISTS,
            f"a live skill named {name} already exists",
            command=command,
            path=live,
            reason=reason,
        )

    if getattr(args, "dry_run", False):
        print(f"[dry-run] would restore: {source} → {live}")
        print(f"[dry-run] reason: {reason}")
        return

    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as err:
        _refuse(
            _RESTORE_REFUSED_UNREADABLE,
            f"cannot read {source}: {err}",
            command=command,
            path=source,
            reason=reason,
        )
        return

    try:
        # "x": never overwrite, even if a live file appeared since the check.
        with live.open("x", encoding="utf-8") as fh:
            fh.write(text)
        source.unlink()
    except OSError as err:
        print(f"Error: {_RESTORE_WRITE_FAILED}: {err}", file=sys.stderr)
        approval._log_decision(
            "rejected",
            command,
            live,
            text,
            source="direct-restore",
            snapshot_path=None,
            reason=f"{reason} [{_RESTORE_WRITE_FAILED}]",
            source_ids=None,
            epistemic_counts=None,
        )
        sys.exit(1)

    logged = approval._log_decision(
        "approved",
        command,
        live,
        text,
        source="direct-restore",
        snapshot_path=None,
        reason=reason,
        source_ids=None,
        epistemic_counts=None,
    )
    print(f"  Restored {name} → {live}")
    if not logged:
        print(
            f"  {_RESTORE_UNRECORDED}: {name} is back in the store but the audit row "
            "did not reach disk. Re-record it by hand.",
            file=sys.stderr,
        )
        sys.exit(1)


def _add_restore_skill_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("name", help="Archived skill filename stem (with or without .md suffix)")
    parser.add_argument(
        "--reason",
        required=True,
        help="Justification recorded in audit.jsonl (required, non-empty)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the move without performing or logging it"
    )


COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="restore-skill",
        help="Move a skill back from skills/.archive/ to the store with an audit row (ADR-0122)",
        handler=_handle_restore_skill,
        tier=Tier.NO_LLM,
        add_arguments=_add_restore_skill_arguments,
    ),
)
