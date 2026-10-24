#!/usr/bin/env python3
"""One-off rewrite of the home path in the MOLTBOOK_HOME files the public sync carries (RFC-0051).

The writers now record paths relative to ``MOLTBOOK_HOME`` (``core/portable_path.py``),
and ``scripts/sync-research-data.sh`` refuses to commit a file that holds the home
path. Files written before that fix — weekly findings and packets, value-layer
readings, RFC-0050's old snapshot manifests — still hold it, and the sync gate stays
shut until they are rewritten. This script rewrites them once.

Which files: exactly what the sync would rsync. Its inline ``--exclude`` patterns, the two ``config/sync-excludes*.txt`` lists and the ``PUBLIC_TOP_LEVEL`` allowlist are read
from ``sync-research-data.sh`` itself and applied by rsync in ``--dry-run`` against
an empty directory, so ``logs/`` (and the episode logs under it) is never listed,
let alone opened.

What changes: every occurrence of the home path, in any letter case, becomes ``~``
(``core.portable_path.redact_home``), nothing else. A ``.json`` file is rewritten
only when the result parses and equals the parsed original with the same
replacement applied to every string; a ``.jsonl`` file, line by line. A file where
that does not hold (a path written with escaped slashes), a non-UTF-8 file, and a
symlink whose target holds the home path are reported and left alone; a symlink
is never followed. A rewrite goes through a temp file in the same directory and
``os.replace``, keeping mode and mtime.

Output: one ``<path>\\t<count>`` line per file (store-relative; names and counts,
never content), then per-top-directory totals. Exit 0 when nothing would be left
holding the home path (dry-run) or nothing is left (``--apply``), 1 otherwise,
2 when the file set cannot be listed.

Run (dev group — ``contemplative_agent`` must be importable)::

    uv run --no-sync python scripts/rewrite_home_paths.py --home ~/.config/moltbook
    uv run --no-sync python scripts/rewrite_home_paths.py --home ~/.config/moltbook --apply
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from contemplative_agent.core.portable_path import redact_home

SYNC_SCRIPT = Path(__file__).resolve().parent / "sync-research-data.sh"


def _sync_rsync_args() -> list[str]:
    """The sync's own transfer rules: its inline excludes, the two config lists
    (--exclude-from, P0-03.2) and the top-level allowlist (P0-03.3)."""
    text = SYNC_SCRIPT.read_text(encoding="utf-8")
    # The catch-all `*` is re-added after the allowlist below; scraped here it
    # would come first and exclude everything.
    excludes = [p for p in re.findall(r"--exclude='([^']*)'", text) if p != "*"]
    # The episode logs live under logs/; a scrape that lost that pattern would
    # list them. Refuse rather than open them.
    if "sync-excludes-public.txt" not in text:
        raise RuntimeError(
            f"`logs/` is excluded by config/sync-excludes-public.txt, which {SYNC_SCRIPT} does not read"
        )
    config = Path(__file__).resolve().parent.parent / "config"
    lists = [config / "sync-excludes.txt", config / "sync-excludes-public.txt"]
    listed = [
        line.strip()
        for path in lists
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if "logs/" not in excludes and "logs/" not in listed:
        raise RuntimeError(f"`logs/` is not among the exclude patterns read from {SYNC_SCRIPT}")
    allow = re.search(r"^PUBLIC_TOP_LEVEL=\(([^)]*)\)", text, re.MULTILINE)
    if not allow:
        raise RuntimeError(f"PUBLIC_TOP_LEVEL not found in {SYNC_SCRIPT}")
    top = allow.group(1).split()
    return [
        *(f"--exclude-from={path}" for path in lists),
        *(f"--exclude={pattern}" for pattern in excludes),
        *[
            arg
            for name in top
            for arg in (
                (f"--include=/{name}",)
                if "." in name
                else (f"--include=/{name}/", f"--include=/{name}/**")
            )
        ],
        "--exclude=*",
    ]


def published_files(store: Path) -> list[str]:
    """Store-relative paths the sync would transfer (files and symlinks, no dirs)."""
    rules = _sync_rsync_args()
    with tempfile.TemporaryDirectory() as empty:
        proc = subprocess.run(
            [
                os.environ.get("RSYNC_BIN") or shutil.which("rsync") or "rsync",
                "-a",
                "-n",
                "-8",
                "--out-format=%n",
                *rules,
                f"{store}/",
                f"{empty}/",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    if proc.returncode != 0:
        raise RuntimeError(f"rsync --dry-run exited {proc.returncode}: {proc.stderr.strip()}")
    return sorted(line for line in proc.stdout.splitlines() if line and not line.endswith("/"))


def _redact_strings(value: object) -> object:
    if isinstance(value, str):
        return redact_home(value)
    if isinstance(value, list):
        return [_redact_strings(item) for item in value]
    if isinstance(value, dict):
        return {redact_home(key): _redact_strings(item) for key, item in value.items()}
    return value


def _json_safe(old: str, new: str, *, lines: bool) -> bool:
    """``new`` parses and means ``old`` with the home redacted in every string."""
    pairs = zip(old.splitlines(), new.splitlines(), strict=True) if lines else [(old, new)]
    try:
        for before, after in pairs:
            if lines and not before.strip():
                continue
            if json.loads(after) != _redact_strings(json.loads(before)):
                return False
    except (ValueError, TypeError):
        return False
    return True


def _write_keeping_metadata(path: Path, text: str) -> None:
    stat = path.stat()
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.chmod(tmp, stat.st_mode & 0o7777)
        os.utime(tmp, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _rewrite_one(path: Path, home: str, *, apply: bool) -> tuple[int, str | None]:
    """(occurrences of the home path, why it stays) for one published file."""
    if path.is_symlink():
        if home in os.readlink(path):
            return 0, "symlink target holds the home path (not followed)"
        return 0, None
    if not path.is_file():
        return 0, None
    data = path.read_bytes()
    # Any letter case, as redact_home and the sync gate match it.
    count = len(re.findall(re.escape(home.encode()), data, flags=re.IGNORECASE))
    if not count:
        return 0, None
    try:
        old = data.decode("utf-8")
    except UnicodeDecodeError:
        return count, "not UTF-8 text"
    new = redact_home(old)
    if path.suffix in (".json", ".jsonl") and not _json_safe(
        old, new, lines=path.suffix == ".jsonl"
    ):
        return count, "JSON would not round-trip (escaped path?)"
    if apply:
        _write_keeping_metadata(path, new)
    return count, None


def scan(store: Path, *, apply: bool) -> int:
    """Rewrite (or, without ``apply``, count) every published file holding the home path."""
    home = str(Path.home())
    if len(home) <= 1:
        print("rewrite_home_paths: HOME is '/'; nothing names a user", file=sys.stderr)
        return 2
    try:
        names = published_files(store)
    except (OSError, RuntimeError) as exc:
        print(f"rewrite_home_paths: cannot list the published set: {exc}", file=sys.stderr)
        return 2

    per_dir: Counter[str] = Counter()
    left: list[str] = []
    for name in names:
        count, reason = _rewrite_one(store / name, home, apply=apply)
        if count:
            print(f"{name}\t{count}")
            per_dir[name.split("/", 1)[0]] += 1
        if reason is not None:
            left.append(f"{name}\t{reason}")

    for top, files in sorted(per_dir.items()):
        print(f"{top}\t{files} file(s)")
    print(f"total\t{sum(per_dir.values())} file(s){'' if apply else ' (dry-run)'}")
    for line in left:
        print(f"LEFT\t{line}")
    return 1 if left else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rewrite the home path in the files the public sync carries (RFC-0051)."
    )
    parser.add_argument("--home", type=Path, required=True, help="the store (MOLTBOOK_HOME)")
    parser.add_argument("--apply", action="store_true", help="rewrite (default: dry-run)")
    args = parser.parse_args(argv)
    store = args.home.expanduser()
    if not store.is_dir():
        print(f"rewrite_home_paths: not a directory: {args.home}", file=sys.stderr)
        return 2
    return scan(store, apply=args.apply)


if __name__ == "__main__":
    sys.exit(main())
