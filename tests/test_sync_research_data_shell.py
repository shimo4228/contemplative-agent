"""Guard on the exclusion list of scripts/sync-research-data.sh.

This script rsyncs `$MOLTBOOK_HOME` into a **public** git repo, so its
`--exclude` list is a disclosure boundary rather than housekeeping. What it
keeps out is either a secret (`credentials.json`), a prompt-injection surface
(`logs/`), or the 768-dim embedding vectors that the export boundary further
down the script deliberately strips out of `knowledge.json`.

The vectors live in two SQLite files, and SQLite runs in the default
`journal_mode=delete`: a write in flight leaves `<name>.sqlite-journal` holding
the old pages beside the database. The script takes no `.run.lock`, so it can
rsync while a scheduled session is mid-transaction — and an exact-basename
exclusion does not cover the journal. Both rules therefore end in `*`
(ADR-0108 D5; the episode store's own case found 2026-09-12).

The test runs rsync with the script's own patterns rather than running the
script, which would want a git remote to push to. Deleting either `*` makes it
fail — that is the point of asserting on a real transfer instead of on the
text of the script.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "sync-research-data.sh"

# The episode / post embedding store (core/episode_embeddings.py) and the
# pattern embedding sidecar (core/pattern_embeddings.py, ADR-0108), each with
# the rollback journal a write in flight leaves next to it.
VECTOR_FILES = (
    "embeddings.sqlite",
    "embeddings.sqlite-journal",
    "pattern-embeddings.sqlite",
    "pattern-embeddings.sqlite-journal",
)


def _excludes() -> list[str]:
    patterns = re.findall(r"--exclude='([^']*)'", SCRIPT.read_text(encoding="utf-8"))
    assert patterns, "no --exclude patterns found in the script"
    return patterns


def _transfer(tmp_path: Path, names: tuple[str, ...]) -> set[str]:
    """rsync a home holding *names* through the script's excludes; return what landed."""
    home = tmp_path / "moltbook"
    dest = tmp_path / "public-repo"
    home.mkdir()
    dest.mkdir()
    for name in names:
        # Only the filename drives the exclusion, so the bytes are a stand-in.
        (home / name).write_bytes(b"SQLite format 3\x00 stand-in")
    (home / "views").mkdir()
    (home / "views" / "self_reflection.md").write_text("# a view\n", encoding="utf-8")

    subprocess.run(
        [
            "rsync",
            "-a",
            "--delete",
            *(f"--exclude={pattern}" for pattern in _excludes()),
            f"{home}/",
            f"{dest}/",
        ],
        check=True,
        capture_output=True,
    )
    return {p.name for p in dest.rglob("*") if p.is_file()}


def test_no_embedding_file_or_its_journal_reaches_the_public_transfer(tmp_path: Path) -> None:
    landed = _transfer(tmp_path, VECTOR_FILES)
    for name in VECTOR_FILES:
        assert name not in landed, f"{name} would be pushed to the PUBLIC data repo"


def test_the_counterweight_research_data_still_goes(tmp_path: Path) -> None:
    """The excludes must stay narrow — this repo exists to publish the store."""
    landed = _transfer(tmp_path, VECTOR_FILES)
    assert "self_reflection.md" in landed


def test_both_sqlite_rules_are_prefix_matches(tmp_path: Path) -> None:
    """Named separately from the transfer test so a failure says which half broke.

    rsync anchors a slash-free pattern to the whole basename, so the two rules
    do not overlap: `embeddings.sqlite*` does not match
    `pattern-embeddings.sqlite`, which is why both are needed.
    """
    patterns = _excludes()
    assert "embeddings.sqlite*" in patterns
    assert "pattern-embeddings.sqlite*" in patterns


# Copies of the raw store keep its embeddings. The first name is the one that
# actually sat in MOLTBOOK_HOME (72 MB, 2026-07-18) and that the former
# `*.bak.*` rule missed: fnmatch wants a dot after `bak` (P0-03.1).
RAW_STORE_COPIES = (
    "knowledge.json.bak-dup-cleanup-20260718",
    "knowledge.json.bak-x",
    "knowledge.json.bak.1",
    "identity.md.bak-20260101",
)


def test_no_copy_of_the_raw_store_reaches_the_public_transfer(tmp_path: Path) -> None:
    landed = _transfer(tmp_path, RAW_STORE_COPIES)
    for name in RAW_STORE_COPIES:
        assert name not in landed, f"{name} would be pushed to the PUBLIC data repo"
    assert "self_reflection.md" in landed


# --- RFC-0051: the home-path gate ---------------------------------------------
#
# These two run the script itself, end to end, under a throwaway HOME: the data
# repo path is derived from $HOME, the repo has no origin (so nothing is pushed)
# and MOLTBOOK_HF_DATASET="" turns the HF upload off.

LEAK_LINE_MARKER = "a line whose text must stay out of the error output"


def _sync_env(tmp_path: Path) -> tuple[dict[str, str], Path, Path]:
    import os

    home = tmp_path / "Users" / "someuser"
    store = home / ".config" / "moltbook"
    (store / "reports" / "analysis").mkdir(parents=True)
    (store / "knowledge.json").write_text("[]\n", encoding="utf-8")
    (store / "reports" / "analysis" / "weekly-2026-10-09.md").write_text(
        "# a clean report\n", encoding="utf-8"
    )
    repo = home / "MyAI_Lab" / "contemplative-agent-data"
    repo.mkdir(parents=True)
    env = {
        "HOME": str(home),
        "PATH": os.environ["PATH"],
        "MOLTBOOK_HF_DATASET": "",
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    subprocess.run(["git", "init", "-q", str(repo)], check=True, env=env)
    return env, store, repo


def _sync(env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=120
    )


def _commits(repo: Path, env: dict[str, str]) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(repo), "log", "--format=%s"], env=env, capture_output=True, text=True
    )
    return out.stdout.splitlines() if out.returncode == 0 else []


def test_a_home_path_bound_for_the_public_repo_stops_the_sync(tmp_path: Path) -> None:
    env, store, repo = _sync_env(tmp_path)
    (store / "pipeline" / "value-layer").mkdir(parents=True)
    (store / "pipeline" / "value-layer" / "value-layer-2026-10-09.json").write_text(
        f'{{"path": "{env["HOME"]}/.config/moltbook/rules", "note": "{LEAK_LINE_MARKER}"}}\n',
        encoding="utf-8",
    )
    proc = _sync(env)
    assert proc.returncode != 0
    assert "pipeline/value-layer/value-layer-2026-10-09.json" in proc.stderr
    assert LEAK_LINE_MARKER not in proc.stderr + proc.stdout
    assert "weekly-2026-10-09.md" not in proc.stderr  # only the leaking file is named
    assert _commits(repo, env) == []


def test_a_clean_store_syncs_as_before(tmp_path: Path) -> None:
    env, _store, repo = _sync_env(tmp_path)
    proc = _sync(env)
    assert proc.returncode == 0, proc.stderr
    commits = _commits(repo, env)
    assert len(commits) == 1 and commits[0].startswith("sync: ")
    assert (repo / "reports" / "analysis" / "weekly-2026-10-09.md").is_file()


def test_a_home_path_in_another_letter_case_also_stops_the_sync(tmp_path: Path) -> None:
    """A writer that lowercases its text (log_anomaly_sweep's signatures) still
    names the user: the file system the path came from is case-insensitive."""
    env, store, repo = _sync_env(tmp_path)
    (store / "reports" / "analysis" / ".anomaly-sweep-state.tsv").write_text(
        f"3\terror opening {env['HOME'].lower()}/x\n", encoding="utf-8"
    )
    proc = _sync(env)
    assert proc.returncode != 0
    assert "reports/analysis/.anomaly-sweep-state.tsv" in proc.stderr
    assert _commits(repo, env) == []


# --- RFC-0053: the gate searches what git can publish, nothing else ----------
#
# `git add -A` stages tracked files and untracked files that are not ignored;
# an ignored file never reaches the public repo. rsync's excludes leave such a
# file untouched (neither updated nor deleted), and scripts/rewrite_home_paths.py
# works on MOLTBOOK_HOME, so a gate that searched the whole working tree stopped
# every daily sync on one file under the data repo's ignored `reports/.private/`
# (2026-10-15..17). The names carry a space and Japanese text because the set
# comes from `git ls-files -z`, and a quoted name (core.quotePath) would miss.


def test_an_ignored_file_holding_the_home_path_does_not_stop_the_sync(tmp_path: Path) -> None:
    env, _store, repo = _sync_env(tmp_path)
    # The shape seen in production: the data repo's own .gitignore (excluded
    # from rsync) ignores `.private`, and rsync leaves `reports/.private/` alone.
    (repo / ".gitignore").write_text(".private\n", encoding="utf-8")
    private = repo / "reports" / ".private"
    private.mkdir(parents=True)
    (private / "週次 メモ.md").write_text(f"see {env['HOME']}/.config/moltbook\n", encoding="utf-8")
    (private / "リンク").symlink_to(f"{env['HOME']}/.config/moltbook/views")
    proc = _sync(env)
    assert proc.returncode == 0, proc.stderr
    commits = _commits(repo, env)
    assert len(commits) == 1 and commits[0].startswith("sync: ")
    tracked = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z"], env=env, capture_output=True, text=True
    ).stdout.split("\0")
    assert not any(".private" in name for name in tracked)  # still not published


def test_an_untracked_unignored_file_holding_the_home_path_still_stops_the_sync(
    tmp_path: Path,
) -> None:
    env, store, repo = _sync_env(tmp_path)
    (repo / ".gitignore").write_text(".private\n", encoding="utf-8")
    (store / "reports" / "analysis" / "週次 メモ.md").write_text(
        f"see {env['HOME']}/.config/moltbook ({LEAK_LINE_MARKER})\n", encoding="utf-8"
    )
    proc = _sync(env)
    assert proc.returncode != 0
    assert "reports/analysis/週次 メモ.md" in proc.stderr
    assert LEAK_LINE_MARKER not in proc.stderr + proc.stdout
    assert "weekly-2026-10-09.md" not in proc.stderr
    assert _commits(repo, env) == []


def test_a_symlink_to_the_home_path_bound_for_the_public_repo_stops_the_sync(
    tmp_path: Path,
) -> None:
    """git stores a link's target as its content, so the target is what is published."""
    env, store, repo = _sync_env(tmp_path)
    (store / "reports" / "analysis" / "最新 リンク").symlink_to(
        f"{env['HOME']}/.config/moltbook/reports/analysis/weekly-2026-10-09.md"
    )
    proc = _sync(env)
    assert proc.returncode != 0
    assert "reports/analysis/最新 リンク" in proc.stderr
    assert _commits(repo, env) == []


def test_a_tracked_file_gone_from_the_working_tree_does_not_break_the_gate(
    tmp_path: Path,
) -> None:
    """`git ls-files --cached` still lists a file rsync --delete removed; the gate
    must not try to read it, and the deletion is what the next commit publishes."""
    env, store, repo = _sync_env(tmp_path)
    assert _sync(env).returncode == 0
    (store / "reports" / "analysis" / "weekly-2026-10-09.md").unlink()
    (store / "reports" / "analysis" / "weekly-2026-10-16.md").write_text(
        "# next week\n", encoding="utf-8"
    )
    proc = _sync(env)
    assert proc.returncode == 0, proc.stderr
    assert len(_commits(repo, env)) == 2
    assert not (repo / "reports" / "analysis" / "weekly-2026-10-09.md").exists()


def test_a_tracked_file_holding_the_home_path_stops_the_sync(tmp_path: Path) -> None:
    """The weekly shape: a file published last week is rewritten with a leak."""
    env, store, repo = _sync_env(tmp_path)
    assert _sync(env).returncode == 0
    (store / "reports" / "analysis" / "weekly-2026-10-09.md").write_text(
        f"# a report\nsee {env['HOME']}/.config/moltbook\n", encoding="utf-8"
    )
    proc = _sync(env)
    assert proc.returncode != 0
    assert "reports/analysis/weekly-2026-10-09.md" in proc.stderr
    assert len(_commits(repo, env)) == 1


def test_a_force_added_file_under_an_ignored_path_is_still_searched(tmp_path: Path) -> None:
    """Ignored but tracked is still published: `--cached` lists it, and rsync's
    excludes keep it out of rewrite_home_paths.py's reach as well."""
    env, _store, repo = _sync_env(tmp_path)
    (repo / ".gitignore").write_text(".private\n", encoding="utf-8")
    private = repo / "reports" / ".private"
    private.mkdir(parents=True)
    note = private / "週次 メモ.md"
    note.write_text("clean at first\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-f", str(note)], check=True, env=env)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "seed"], check=True, env=env)
    note.write_text(f"see {env['HOME']}/.config/moltbook\n", encoding="utf-8")
    proc = _sync(env)
    assert proc.returncode != 0
    assert "reports/.private/週次 メモ.md" in proc.stderr
    assert _commits(repo, env) == ["seed"]


def test_a_failing_file_listing_stops_the_sync(tmp_path: Path) -> None:
    """Fail closed: an empty list from a failed `git ls-files` must not read as clean."""
    import shutil

    env, _store, repo = _sync_env(tmp_path)
    real_git = shutil.which("git", path=env["PATH"])
    assert real_git
    stub = tmp_path / "stub-bin"
    stub.mkdir()
    (stub / "git").write_text(
        "#!/bin/sh\n"
        'case "$*" in *ls-files*) echo "fatal: index file corrupt" >&2; exit 128;; esac\n'
        f'exec "{real_git}" "$@"\n',
        encoding="utf-8",
    )
    (stub / "git").chmod(0o755)
    proc = _sync({**env, "PATH": f"{stub}:{env['PATH']}"})
    assert proc.returncode != 0
    assert "could not search" in proc.stderr
    assert _commits(repo, env) == []
