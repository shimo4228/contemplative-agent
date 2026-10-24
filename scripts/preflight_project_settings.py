#!/usr/bin/env python3
"""Preflight read of the project-level Claude Code settings (P1-10.13).

stdlib-only (called by bare ``python3`` from scripts/weekly-pipeline.sh).

The unattended weekly session runs with ``--setting-sources project``, so an
untracked ``.claude/settings.json`` in the checkout is part of its effective
permission set (``settings.local.json`` is the ``local`` source and is NOT
loaded, so it is reported but never judged): ``--allowedTools`` only ADDS
and settings allow rules are consulted first (see the header of
tests/test_weekly_pipeline_session_scope_shell.py, mechanics 1-2). Nothing
tracked pins that file, so this stage reads it before the session starts.

Output: ``key=value`` lines on stdout, one audit row's worth of fields:

  settings_local    1 when settings.local.json exists (informational only)
  settings_files    names found (comma separated, ``none`` when absent)
  settings_sha256   sha256 over the found files in name order (``none`` if none)
  allow_rules       number of ``permissions.allow`` entries
  hooks             1 when any file defines a non-empty ``hooks`` key
  extra_dirs        number of ``permissions.additionalDirectories`` entries
  parse_error       1 when a found file is not a JSON object (fails closed)
  widen             1 when allow_rules, hooks, extra_dirs or parse_error is set

Exit 0 always for a readable run; the caller decides what ``widen=1`` means
(skip only the headless report stage, reason PREFLIGHT_PROJECT_SETTINGS_WIDEN;
deterministic intakes keep running). Exit 2 on a usage error.

Consumption plan (ADR-0101): (a) the Saturday gate Step 0 reads the
``project_settings`` row of weekly-pipeline-audit.jsonl through PIPELINE-STATUS
every week; (b) one skipped report stage means "the unattended session's permissions were
widened" -- remove the offending rules from settings.json and re-run; (c) retire this
whole stage when the chain moves to ``--setting-sources ""`` (or the stdin
prompt variant) so no project settings are loaded at all.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

# Only .claude/settings.json: `--setting-sources project` never loads
# settings.local.json (that is the `local` source), so a file there cannot
# widen the unattended session. Its presence is reported, never judged.
SETTINGS_NAMES = ("settings.json",)
LOCAL_NAME = "settings.local.json"


def inspect(project_root: Path) -> dict[str, str]:
    claude_dir = project_root / ".claude"
    found: list[Path] = [claude_dir / n for n in SETTINGS_NAMES if (claude_dir / n).is_file()]
    digest = hashlib.sha256()
    allow = extra = 0
    hooks = parse_error = 0
    for path in found:
        raw = path.read_bytes()
        digest.update(path.name.encode() + b"\0" + raw + b"\0")
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            parse_error = 1
            continue
        if not isinstance(data, dict):
            parse_error = 1
            continue
        perms = data.get("permissions")
        if isinstance(perms, dict):
            rules = perms.get("allow")
            if isinstance(rules, list):
                allow += len(rules)
            dirs = perms.get("additionalDirectories")
            if isinstance(dirs, list):
                extra += len(dirs)
        if data.get("hooks"):
            hooks = 1
    widen = int(bool(allow or hooks or extra or parse_error))
    return {
        "settings_local": str(int((claude_dir / LOCAL_NAME).is_file())),
        "settings_files": ",".join(p.name for p in found) or "none",
        "settings_sha256": digest.hexdigest() if found else "none",
        "allow_rules": str(allow),
        "hooks": str(hooks),
        "extra_dirs": str(extra),
        "parse_error": str(parse_error),
        "widen": str(widen),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--project-root", type=Path, required=True)
    args = parser.parse_args()
    for key, value in inspect(args.project_root).items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
