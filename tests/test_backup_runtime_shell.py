"""End-to-end guards for ``scripts/backup-runtime.sh`` (the weekly launchd job).

T-LOGROT-OLLAMA: ``logs/ollama-serve.log`` reached 96.5 MB on 2026-08-01 and was
about to cross GitHub's 100 MB hard limit at the next weekly run — which would
have failed the push and stalled the off-site copy of the episode logs, the one
thing this backup exists to protect. An Ollama server log is re-derivable
operational noise, not research data, so it is excluded from the mirror rather
than allowed to hold the push hostage.

Two invariants are pinned here, both invisible in a passing run:

1. **No ``ollama-serve.log`` family member reaches the mirror** — current file or
   rotated ``.N.gz`` generation.
2. **A copy already in the mirror is removed.** ``rsync --exclude`` shields the
   destination from ``--delete`` (the same trap the ``credentials.json`` belt-and-
   suspenders was added for), so an exclude alone would leave the 96 MB blob in
   place forever.

Those two are checked on final git state, which cannot tell the two mechanisms
apart — the trailing ``rm -f`` alone would satisfy both. So the excludes get
their own test that runs rsync with the script's own patterns and nothing else:
delete the ``--exclude`` lines and that one fails while the others still pass
(mutation-tested, python review 2026-08-01). The excludes are what stops 96 MB
from being copied every week in the first place.

The counterweight test guards the other direction: the exclude must not widen.
Episode logs, reports and audit trails are what the backup is for.

macOS-only alongside the other shell suites: same rsync/BSD environment as the
job actually runs in.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="backup-runtime.sh runs under macOS rsync/launchd"
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "backup-runtime.sh"

OLLAMA_LOG = "logs/ollama-serve.log"
OLLAMA_ROTATED = "logs/ollama-serve.log.1.gz"
# Shares the excluded prefix but is not part of the family — a `.log*` glob
# would sweep it out of the mirror silently (codex review, 2026-08-01).
NEAR_PREFIX = "logs/ollama-serve.logger.jsonl"
EPISODE_LOG = "logs/2026-01-01.jsonl"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _tracked(repo: Path) -> set[str]:
    """Exact tracked paths. Substring checks lie here: `ollama-serve.logger.jsonl`
    contains `ollama-serve.log`."""
    return set(_git(repo, "ls-files").splitlines())


def _make_home(tmp_path: Path) -> Path:
    """A minimal MOLTBOOK_HOME: the two log families, a report, and the secret."""
    home = tmp_path / "moltbook"
    (home / "logs").mkdir(parents=True)
    (home / "reports").mkdir(parents=True)

    (home / OLLAMA_LOG).write_text("slot launch_slot_: id 0\n" * 100, encoding="utf-8")
    (home / OLLAMA_ROTATED).write_bytes(b"\x1f\x8b\x08 not really gzip, only the name matters")
    (home / NEAR_PREFIX).write_text('{"type":"near-prefix"}\n', encoding="utf-8")
    (home / EPISODE_LOG).write_text('{"type":"episode"}\n', encoding="utf-8")
    (home / "logs" / "api-audit.jsonl").write_text('{"type":"api"}\n', encoding="utf-8")
    (home / "reports" / "weekly.md").write_text("# Weekly\n", encoding="utf-8")
    (home / "knowledge.json").write_text(
        json.dumps([{"id": "p1", "text": "pattern", "embedding": [0.1, 0.2]}]),
        encoding="utf-8",
    )
    # Contents are irrelevant — only the filename drives the exclusion. Kept
    # keyword-free so the pre-commit secret scan has nothing to flag.
    (home / "credentials.json").write_text(
        '{"stand_in_for": "the API credential"}', encoding="utf-8"
    )
    return home


def _make_backup_repo(tmp_path: Path) -> Path:
    """A git repo with a local bare origin, so `git push` works offline."""
    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True
    )

    repo = tmp_path / "backup"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("# Backup mirror\n", encoding="utf-8")
    (repo / ".gitignore").write_text("credentials.json\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-u", "origin", "main")
    return repo


def _run(home: Path, repo: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Drive the real script. `gh` is stubbed PRIVATE — no network, no real repo."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "gh"
    stub.write_text("#!/bin/bash\necho PRIVATE\n", encoding="utf-8")
    stub.chmod(0o755)

    fake_home = tmp_path / "fakehome"
    fake_home.mkdir(exist_ok=True)

    env = dict(os.environ)
    env["MOLTBOOK_HOME"] = str(home)
    env["MOLTBOOK_BACKUP_REPO"] = str(repo)
    env["HOME"] = str(fake_home)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    return subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
        timeout=300,
    )


def test_the_excludes_alone_keep_the_family_out_of_the_transfer(tmp_path: Path) -> None:
    """Runs rsync with the script's own patterns and no cleanup step behind it.

    The end-state tests below pass even with the `--exclude` lines deleted,
    because `rm -f` removes the family before `git add`. This one does not.
    """
    home = _make_home(tmp_path)
    dest = tmp_path / "transfer"
    dest.mkdir()

    excludes = re.findall(r"--exclude='([^']*)'", SCRIPT.read_text(encoding="utf-8"))
    assert excludes, "no --exclude patterns found in the script"
    subprocess.run(
        [
            "rsync",
            "-a",
            "--delete",
            *(f"--exclude={pattern}" for pattern in excludes),
            f"{home}/",
            f"{dest}/",
        ],
        check=True,
        capture_output=True,
    )

    assert not (dest / OLLAMA_LOG).exists(), "rsync copied the live log — the exclude is gone"
    assert not (dest / OLLAMA_ROTATED).exists()
    assert (dest / NEAR_PREFIX).exists()
    assert (dest / EPISODE_LOG).exists()


def test_ollama_serve_log_never_reaches_the_mirror(tmp_path: Path) -> None:
    home = _make_home(tmp_path)
    repo = _make_backup_repo(tmp_path)

    result = _run(home, repo, tmp_path)

    assert result.returncode == 0, result.stderr
    tracked = _tracked(repo)
    assert OLLAMA_LOG not in tracked
    assert OLLAMA_ROTATED not in tracked
    assert not (repo / OLLAMA_LOG).exists()
    assert not (repo / OLLAMA_ROTATED).exists()


def test_ollama_copy_already_in_the_mirror_is_removed(tmp_path: Path) -> None:
    """`--exclude` shields the destination from `--delete`; the copy must still go."""
    home = _make_home(tmp_path)
    repo = _make_backup_repo(tmp_path)
    (repo / "logs").mkdir()
    (repo / OLLAMA_LOG).write_text("a 96 MB blob, in spirit\n", encoding="utf-8")
    (repo / OLLAMA_ROTATED).write_bytes(b"\x1f\x8b\x08 a stale generation")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "seed the stale copies")

    result = _run(home, repo, tmp_path)

    assert result.returncode == 0, result.stderr
    tracked = _tracked(repo)
    for stale in (OLLAMA_LOG, OLLAMA_ROTATED):
        assert not (repo / stale).exists()
        assert stale not in tracked


def test_research_data_is_still_mirrored_and_the_secret_is_not(tmp_path: Path) -> None:
    """The counterweight: the exclude must stay narrow."""
    home = _make_home(tmp_path)
    repo = _make_backup_repo(tmp_path)

    result = _run(home, repo, tmp_path)

    assert result.returncode == 0, result.stderr
    tracked = _tracked(repo)
    assert EPISODE_LOG in tracked
    assert NEAR_PREFIX in tracked, "the exclude must match the log family, not its prefix"
    assert "logs/api-audit.jsonl" in tracked
    assert "reports/weekly.md" in tracked
    assert "credentials.json" not in tracked
    # knowledge.json is regenerated embedding-free rather than mirrored.
    assert "embedding" not in (repo / "knowledge.json").read_text(encoding="utf-8")
