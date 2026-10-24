#!/usr/bin/env python3
"""Number and publish the weekly chain's draft RFCs at the Saturday gate (P2-03.3).

The unattended chain files drafts into `rfcs/.inbox/` (gitignored), already
carrying `filed_by:` / `producer:` frontmatter. Nothing there is numbered or
tracked, so an unattended run leaves `git status --short rfcs/` empty. The
gate (weekly-gate Step 6d), after its sensitivity pass, calls:

  list                       the inbox, one name per line
  adopt [--only NAME ...]    number (max existing NNNN + 1; gaps never reused),
                             move to rfcs/NNNN-<name>.md, append the index row
                             to rfcs/README.md, and — only when a claims
                             recorder exists — record the spawn there too

A draft that is withdrawn at the gate is simply deleted from the inbox.
Numbering lives here, not in the chain, so it is assigned once, by the
process that also commits.

Read/write scope: `rfcs/` and `rfcs/.inbox/` only. Stdlib only.
Consumption plan (ADR-0101): (a) the gate session runs `adopt` once per Saturday
at Step 6d; (b) one run decides which drafts reach the public ledger; (c)
removal: when drafts stop being filed by the chain, or P2-05.1 replaces the
publication step.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.md$")
ENTRY_RE = re.compile(r"^(\d{4})-.+\.md$")


def next_number(tasks_dir: Path) -> int:
    nums = [int(m.group(1)) for p in tasks_dir.glob("[0-9][0-9][0-9][0-9]-*.md") if (m := ENTRY_RE.match(p.name))]
    return max(nums, default=0) + 1


def frontmatter_value(text: str, key: str) -> str:
    head = text.split("\n---\n", 1)[0]
    m = re.search(rf"^{re.escape(key)}:\s*(.+?)(?:\s+#.*)?$", head, re.M)
    return m.group(1).strip() if m else ""


def title_of(text: str) -> str:
    """First non-heading, non-empty body line (the summary claims.py shows)."""
    parts = text.split("\n---\n", 1)
    body = parts[1] if len(parts) == 2 else text
    for line in body.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line[:140]
    return "(no summary)"


def append_index_row(readme: Path, number: str, filename: str, title: str) -> None:
    if not readme.is_file():
        return
    lines = readme.read_text(encoding="utf-8").splitlines(keepends=True)
    last_row = max((i for i, ln in enumerate(lines) if re.match(r"\| \[\d{4}\]\(", ln)), default=None)
    row = f"| [{number}]({filename}) | {title.replace('|', '/')} |\n"
    if last_row is None:
        lines.append(row)
    else:
        if not lines[last_row].endswith("\n"):
            lines[last_row] += "\n"
        lines.insert(last_row + 1, row)
    readme.write_text("".join(lines), encoding="utf-8")


def spawn(claims_py: Path | None, project_root: Path, task_id: str, name: str, filed_by: str, producer: str) -> str:
    """Optional private record. Returns '' or a reason code; never raises."""
    if claims_py is None or not claims_py.is_file():
        return ""
    cmd = [sys.executable, str(claims_py), "spawn", task_id, "--origin", "gate",
           "--note", f"{filed_by or 'weekly'} diagnosis ({name})"]
    if producer:
        cmd += ["--producer", producer]
    try:
        done = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return "SPAWN_RECORD_FAIL"
    return "" if done.returncode == 0 else "SPAWN_RECORD_FAIL"


def cmd_list(inbox: Path) -> int:
    for p in sorted(inbox.glob("*.md")):
        print(p.name)
    return 0


def cmd_adopt(args: argparse.Namespace) -> int:
    inbox, tasks = args.inbox_dir, args.tasks_dir
    names = args.only or [p.name for p in sorted(inbox.glob("*.md"))]
    rc = 0
    for name in names:
        src = inbox / name
        if not NAME_RE.match(name) or not src.is_file():
            print(f"SKIPPED {name}: not a conforming inbox file", file=sys.stderr)
            rc = 1
            continue
        number = f"{next_number(tasks):04d}"
        dest = tasks / f"{number}-{name}"
        if dest.exists():
            print(f"SKIPPED {name}: {dest.name} already exists", file=sys.stderr)
            rc = 1
            continue
        text = src.read_text(encoding="utf-8")
        src.rename(dest)
        append_index_row(tasks / "README.md", number, dest.name, title_of(text))
        reason = spawn(
            args.claims_py, args.project_root, f"RFC-{number}", name,
            frontmatter_value(text, "filed_by"), frontmatter_value(text, "producer"),
        )
        print(f"adopted RFC-{number} {dest.name}" + (f" ({reason})" if reason else ""))
    return rc


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tasks-dir", type=Path, default=root / "rfcs")
    parser.add_argument("--inbox-dir", type=Path, default=None)
    parser.add_argument("--project-root", type=Path, default=root)
    parser.add_argument("--claims-py", type=Path, default=None, help="optional private recorder")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    adopt = sub.add_parser("adopt")
    adopt.add_argument("--only", nargs="+", metavar="NAME")
    args = parser.parse_args()
    if args.inbox_dir is None:
        args.inbox_dir = args.tasks_dir / ".inbox"
    if not args.inbox_dir.is_dir():
        print("inbox is empty (no directory)", file=sys.stderr)
        return 0
    return cmd_list(args.inbox_dir) if args.cmd == "list" else cmd_adopt(args)


if __name__ == "__main__":
    sys.exit(main())
