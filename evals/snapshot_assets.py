#!/usr/bin/env python3
"""Snapshot the agent's evolving prompt assets for reproducible evals.

The four assets that distill/amendment rewrite over time (identity.md,
constitution/, skills/, rules/) are copied from the live MOLTBOOK_HOME into
``evals/fixtures/agent_home/`` so an eval run measures a pinned prompt state,
not whatever the agent has since become. Template prompts (config/prompts/)
need no snapshot: pointing MOLTBOOK_HOME at the fixture dir (which has no
prompts/ override) pins them to the repo commit via the normal precedence.

Copying is allowlist-only — MOLTBOOK_HOME also holds credentials.json,
knowledge.json and logs, none of which may enter the repo. Only ``*.md``
files of the four assets are taken, matching what ``_load_md_files`` /
``load_constitution`` actually read; symlinks and anything resolving outside
the source tree are refused outright (a symlink named ``leak.md`` pointing
at ``credentials.json`` would otherwise defeat the extension allowlist).

The manifest records only the aggregate hash and a file count: per-file
hashes would trip the harness secret scan's entropy detector 40+ times and
run_eval recomputes everything from disk anyway (``hash_tree``).

Snapshots are LLM-distilled output and therefore untrusted data: review the
diff and run the secret scan before committing (ADR-0089).

Usage:
    uv run python evals/snapshot_assets.py            # from live ~/.config/moltbook
    uv run python evals/snapshot_assets.py --source /path/to/moltbook-home
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "agent_home"

# The complete set of things this script will ever copy. Anything not listed
# here stays out of the repo by construction.
ASSET_DIRS = ("constitution", "skills", "rules")
ASSET_FILES = ("identity.md",)


class SnapshotError(ValueError):
    """The snapshot cannot proceed safely (bad source, escaping path, …)."""


def _default_source() -> Path:
    env = os.environ.get("MOLTBOOK_HOME")
    return Path(env) if env else Path.home() / ".config" / "moltbook"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_contained(path: Path, root: Path) -> None:
    """Refuse symlinks and anything resolving outside *root*."""
    if path.is_symlink():
        raise SnapshotError(f"refusing to copy symlink: {path}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise SnapshotError(f"asset escapes source tree: {path}")


def _iter_asset_files(root: Path) -> Iterator[tuple[str, Path]]:
    """Yield (relative_name, path) over the asset allowlist under *root*.

    The single walker both snapshot() and hash_tree() use — if the allowlist
    ever changes, the copied set and the hashed set move together, so
    ``assets_sha256`` always describes exactly what was pinned.
    """
    for name in ASSET_FILES:
        p = root / name
        if p.exists():
            yield name, p
    for dirname in ASSET_DIRS:
        d = root / dirname
        if not d.is_dir():
            continue
        for md in sorted(d.glob("*.md")):
            yield f"{dirname}/{md.name}", md


def snapshot(source: Path, dest: Path) -> dict[str, str]:
    """Copy the four prompt assets from *source* into *dest*.

    Returns {relative_path: sha256} for every copied file. Existing asset
    dirs under *dest* are replaced wholesale so retired skills do not linger.
    Raises SnapshotError on a missing source/identity, symlinked assets, or
    a *dest* outside the repo fixture area (rmtree must never point at an
    arbitrary directory a typo produced).
    """
    if not source.is_dir():
        raise SnapshotError(f"source is not a directory: {source}")
    if not (source / ASSET_FILES[0]).is_file():
        raise SnapshotError(f"missing asset: {source / ASSET_FILES[0]}")
    evals_root = Path(__file__).resolve().parent
    if not dest.resolve().is_relative_to(evals_root):
        raise SnapshotError(f"dest must live under {evals_root} (got {dest})")

    dest.mkdir(parents=True, exist_ok=True)
    for dirname in ASSET_DIRS:
        dst_dir = dest / dirname
        if dst_dir.is_dir():
            shutil.rmtree(dst_dir)
        dst_dir.mkdir()

    hashes: dict[str, str] = {}
    for rel, src in _iter_asset_files(source):
        _check_contained(src, source)
        target = dest / rel
        shutil.copyfile(src, target)
        hashes[rel] = _sha256(target)
    return hashes


def hash_tree(root: Path) -> dict[str, str]:
    """Hash the asset files under *root* without copying anything.

    Walks the same allowlist as :func:`snapshot`, so run_eval can recompute
    the fixture's aggregate hash at run time instead of trusting a possibly
    stale manifest.json.
    """
    return {rel: _sha256(p) for rel, p in _iter_asset_files(root)}


def aggregate_sha256(hashes: dict[str, str]) -> str:
    """Order-independent digest over {relative_path: sha256}.

    Entries are sorted before hashing, so insertion order never matters; an
    empty tree is refused because its digest would look like a legitimate
    pin and quietly satisfy the comparability gate.
    """
    if not hashes:
        raise SnapshotError("refusing to hash an empty asset tree")
    lines = "".join(f"{rel}:{digest}\n" for rel, digest in sorted(hashes.items()))
    return hashlib.sha256(lines.encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=_default_source())
    parser.add_argument("--dest", type=Path, default=FIXTURE_DIR)
    args = parser.parse_args()

    try:
        hashes = snapshot(args.source, args.dest)
        aggregate = aggregate_sha256(hashes)
    except SnapshotError as exc:
        print(f"[snapshot] {exc}", file=sys.stderr)
        return 2

    # ~-normalized source: no absolute home path in a public repo, and the
    # manifest stays reproducible across machines.
    try:
        source_display = "~/" + str(args.source.resolve().relative_to(Path.home()))
    except ValueError:
        source_display = str(args.source)

    manifest = {
        "snapshot_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source_display,
        "file_count": len(hashes),
        "aggregate_sha256": aggregate,
    }
    manifest_path = args.dest / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"snapshot: {len(hashes)} files -> {args.dest}")
    print(f"aggregate_sha256: {manifest['aggregate_sha256']}")
    print("review the diff and run the secret scan before committing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
