"""Repo-hygiene gate: a tracked symlink must point at a tracked target.

``.codex/hooks/codemap-freshness-check.sh`` was a *tracked* symlink pointing at
``.claude/hooks/codemap-freshness-check.sh``, which ``.gitignore`` excluded, so
it resolved only in the author's main checkout where the target happened to sit
untracked on disk. Every clone and every ``git worktree`` got the link without
its target, and ``.claude/verify.sh`` — which feeds ``git ls-files '*.sh'``
straight to shellcheck — failed there on ``openBinaryFile: does not exist``
(T-VERIFY-WORKTREE-DANGLING-SH, 2026-08-16).

The defect is not the one file — it is a tracked object depending on an
untracked one, which git cannot reproduce anywhere else. So this gate asserts
the dependency rather than the symptom: dropping an untracked file back into
place would un-dangle the link while leaving every clone broken, and a link
whose target exists but is *not tracked* therefore fails too.

A tracked *regular* file absent from the working tree is a different situation
(sparse checkout) and is deliberately not asserted here.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _tracked_names() -> set[str]:
    result = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "ls-files", "-z"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("not a git checkout")
    return {name for name in result.stdout.split("\0") if name}


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_tracked_symlinks_point_at_tracked_targets() -> None:
    tracked = _tracked_names()
    offenders = []
    for name in tracked:
        link = PROJECT_ROOT / name
        if not link.is_symlink():
            continue
        if not link.exists():
            offenders.append(f"{name} -> {link.readlink()} (missing)")
            continue
        resolved = link.resolve()
        try:
            target = str(resolved.relative_to(PROJECT_ROOT))
        except ValueError:
            offenders.append(f"{name} -> {resolved} (outside the repo)")
            continue
        # git has no directory entries, so a link onto a directory is carried
        # whenever git tracks anything beneath it.
        prefix = f"{target}/"
        if target not in tracked and not any(n.startswith(prefix) for n in tracked):
            offenders.append(f"{name} -> {target} (untracked)")

    assert not offenders, (
        "tracked symlink(s) depend on something git does not carry, so they "
        "break in every clone and worktree: " + "; ".join(sorted(offenders))
    )
