"""scripts/restore-drill-check.sh against a fixture live home and backup mirror (P2-04.19)."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "restore-drill-check.sh"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**os.environ, **GIT_ENV},
    )


def _populate(home: Path, rows: int = 3) -> None:
    (home / "logs" / "episodes").mkdir(parents=True)
    for day in ("2026-10-01", "2026-10-02"):
        (home / "logs" / "episodes" / f"{day}.jsonl").write_text(f'{{"day": "{day}"}}\n')
    (home / "knowledge.json").write_text(json.dumps([{"pattern": f"p{i}"} for i in range(rows)]))


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    live, mirror = tmp_path / "live", tmp_path / "mirror"
    live.mkdir()
    mirror.mkdir()
    _populate(live)
    _populate(mirror)
    _git(mirror, "init", "-q")
    _git(mirror, "add", "-A")
    _git(mirror, "commit", "-q", "-m", "backup")
    # every live file predates the backup commit
    old = time.time() - 3600
    for p in live.rglob("*"):
        if p.is_file():
            os.utime(p, (old, old))
    return live, mirror


def _check(live: Path, mirror: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), "--repo", str(mirror), "--live", str(live)],
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_a_faithful_mirror_passes(tmp_path):
    live, mirror = _fixture(tmp_path)
    proc = _check(live, mirror)
    assert proc.returncode == 0, proc.stderr
    assert "all checks passed" in proc.stdout


def test_a_missing_episode_file_in_the_mirror_fails(tmp_path):
    live, mirror = _fixture(tmp_path)
    (mirror / "logs" / "episodes" / "2026-10-02.jsonl").unlink()
    _git(mirror, "add", "-A")
    _git(mirror, "commit", "-q", "-m", "lost a file")
    proc = _check(live, mirror)
    assert proc.returncode == 1
    assert "logs/episodes differ" in proc.stderr


def test_a_live_file_newer_than_the_backup_is_not_a_difference(tmp_path):
    live, mirror = _fixture(tmp_path)
    newer = live / "logs" / "episodes" / "2026-10-03.jsonl"
    newer.write_text("{}\n")
    future = time.time() + 3600
    os.utime(newer, (future, future))
    assert _check(live, mirror).returncode == 0


def test_a_knowledge_row_count_mismatch_fails(tmp_path):
    live, mirror = _fixture(tmp_path)
    (mirror / "knowledge.json").write_text(json.dumps([{"pattern": "p0"}]))
    _git(mirror, "add", "-A")
    _git(mirror, "commit", "-q", "-m", "fewer rows")
    proc = _check(live, mirror)
    assert proc.returncode == 1 and "knowledge.json rows differ" in proc.stderr


def test_an_unclonable_repo_fails(tmp_path):
    live, _mirror = _fixture(tmp_path)
    proc = _check(live, tmp_path / "does-not-exist")
    assert proc.returncode == 1 and "could not clone" in proc.stderr
