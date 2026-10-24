"""Text-level guards on the shared exclude lists and the scripts that read them.

These need no rsync, so they run on every platform (the transfer-level
counterparts are in test_sync_research_data_shell.py and, on macOS,
test_backup_runtime_shell.py). P0-03.2 / .3 / .6 / .16.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG = REPO_ROOT / "config"
SYNC = (REPO_ROOT / "scripts" / "sync-research-data.sh").read_text(encoding="utf-8")
BACKUP = (REPO_ROOT / "scripts" / "backup-runtime.sh").read_text(encoding="utf-8")


def _lines(name: str) -> list[str]:
    return (CONFIG / name).read_text(encoding="utf-8").splitlines()


def test_both_scripts_read_the_same_shared_exclude_file() -> None:
    needle = '--exclude-from="$SCRIPT_DIR/../config/sync-excludes.txt"'
    assert needle in SYNC
    assert needle in BACKUP


def test_both_scripts_resolve_one_rsync_and_use_it() -> None:
    for text in (SYNC, BACKUP):
        assert "resolve_rsync_bin" in text
        assert '"$RSYNC_BIN" -a --delete' in text
    lib = (REPO_ROOT / "scripts" / "lib-rsync.sh").read_text(encoding="utf-8")
    assert "openrsync" in lib and "ERROR:" in lib


def test_the_shared_list_carries_the_secret_and_lock_family() -> None:
    names = {ln.strip() for ln in _lines("sync-excludes.txt") if ln.strip() and ln[0] != "#"}
    assert {"credentials.json", "*.env", ".*.lock", "*.tmp"} <= names


def test_the_public_list_carries_gc_trash_and_last_markers() -> None:
    names = {ln.strip() for ln in _lines("sync-excludes-public.txt") if ln.strip() and ln[0] != "#"}
    assert {"_gc_trash/", ".last_*", "*.bak*", "logs/"} <= names
    # receiver-owned names must never be on a retractable list
    for forbidden in ("knowledge.json", "README.md", "DATACARD.md", "NOTICE", "LICENSE"):
        assert forbidden not in names


def test_the_backup_removes_a_seeded_cloud_env() -> None:
    assert "rm -f credentials.json cloud.env" in BACKUP


def test_the_sync_script_never_forces_a_push() -> None:
    assert "--force" not in SYNC


def test_the_sync_script_reads_the_secret_pattern_file() -> None:
    assert "config/secret-patterns.txt" in SYNC


def test_every_line_of_the_secret_pattern_file_is_a_pattern() -> None:
    """`grep -f` treats a blank or comment line as a pattern (a blank matches everything)."""
    lines = _lines("secret-patterns.txt")
    assert lines
    for line in lines:
        assert line.strip() and not line.startswith("#"), repr(line)
    text = "\n".join(lines)
    assert "api_key" not in text and "Bearer " not in text.replace("Authorization: Bearer ", "")


def test_the_generated_gitignore_ignores_the_withheld_family(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "gen_data_gitignore", REPO_ROOT / "scripts" / "gen-data-gitignore.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    repo = tmp_path / "data"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / ".gitignore").write_text(mod.render(), encoding="utf-8")
    for must_ignore in (
        "credentials.json",
        "cloud.env",
        "logs/x.jsonl",
        "embeddings.sqlite-journal",
        "pattern-embeddings.sqlite",
        "relevance_cache.json",
        "knowledge.json.bak-x",
        "x.tmp",
        ".run.lock",
        ".staged.lock",
        ".archive/a.md",
        "skills/_gc_trash/a.md",
        "skills/.last_insight",
    ):
        out = subprocess.run(
            ["git", "-C", str(repo), "check-ignore", "-q", must_ignore], capture_output=True
        )
        assert out.returncode == 0, f"{must_ignore} is not ignored"
    for must_publish in ("README.md", "DATACARD.md", "knowledge.json", "skills/a.md", "NOTICE"):
        out = subprocess.run(
            ["git", "-C", str(repo), "check-ignore", "-q", must_publish], capture_output=True
        )
        assert out.returncode == 1, f"{must_publish} would be ignored"
