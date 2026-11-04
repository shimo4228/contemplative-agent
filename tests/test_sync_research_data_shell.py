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

import subprocess
from pathlib import Path

import pytest

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


CONFIG = REPO_ROOT / "config"
EXCLUDE_LISTS = (CONFIG / "sync-excludes.txt", CONFIG / "sync-excludes-public.txt")


def _excludes() -> list[str]:
    """The patterns the script reads with --exclude-from (P0-03.2 / .3)."""
    patterns = [
        line.strip()
        for path in EXCLUDE_LISTS
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert patterns, "no exclude patterns found in the config lists"
    return patterns


def _transfer(tmp_path: Path, names: tuple[str, ...]) -> set[str]:
    """Run the real sync over a home holding *names*; return the file names that landed.

    The names sit inside `skills/`, an allowlisted directory, so it is the
    exclude lists that keep them out and not the top-level allowlist.
    """
    env, store, repo = _sync_env(tmp_path)
    skills = store / "skills"
    skills.mkdir()
    for name in names:
        # Only the filename drives the exclusion, so the bytes are a stand-in.
        (skills / name).write_bytes(b"SQLite format 3\x00 stand-in")
    (store / "views").mkdir(exist_ok=True)
    (store / "views" / "self_reflection.md").write_text("# a view\n", encoding="utf-8")
    proc = _sync(env)
    assert proc.returncode == 0, proc.stderr
    return {
        p.name for p in repo.rglob("*") if p.is_file() and ".git" not in p.relative_to(repo).parts
    }


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
    # A weekly document the unattended run must leave home (P2-05.1) ...
    (store / "reports" / "analysis" / "weekly-2026-10-09.md").write_text(
        "# a clean report\n", encoding="utf-8"
    )
    # ... and a file of the machine layer it publishes. The gate tests below
    # put their leaks under views/ for that reason: a path the daily run sends.
    (store / "views").mkdir(exist_ok=True)
    (store / "views" / "view-2026-10-09.md").write_text("# a clean view\n", encoding="utf-8")
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


def _sync(env: dict[str, str], *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=120
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
    assert "view-2026-10-09.md" not in proc.stderr  # only the leaking file is named
    assert _commits(repo, env) == []


def test_a_clean_store_syncs_as_before(tmp_path: Path) -> None:
    env, _store, repo = _sync_env(tmp_path)
    proc = _sync(env)
    assert proc.returncode == 0, proc.stderr
    commits = _commits(repo, env)
    assert len(commits) == 1 and commits[0].startswith("sync: ")
    assert (repo / "views" / "view-2026-10-09.md").is_file()


def test_a_home_path_in_another_letter_case_also_stops_the_sync(tmp_path: Path) -> None:
    """A writer that lowercases its text (log_anomaly_sweep's signatures) still
    names the user: the file system the path came from is case-insensitive.
    The sweep's own state file sits in reports/analysis/, which the daily run no
    longer sends (P2-05.1), so the same text is placed on a path it does send."""
    env, store, repo = _sync_env(tmp_path)
    (store / "views" / ".anomaly-sweep-state.tsv").write_text(
        f"3\terror opening {env['HOME'].lower()}/x\n", encoding="utf-8"
    )
    proc = _sync(env)
    assert proc.returncode != 0
    assert "views/.anomaly-sweep-state.tsv" in proc.stderr
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
    (store / "views" / "週次 メモ.md").write_text(
        f"see {env['HOME']}/.config/moltbook ({LEAK_LINE_MARKER})\n", encoding="utf-8"
    )
    proc = _sync(env)
    assert proc.returncode != 0
    assert "views/週次 メモ.md" in proc.stderr
    assert LEAK_LINE_MARKER not in proc.stderr + proc.stdout
    assert "view-2026-10-09.md" not in proc.stderr
    assert _commits(repo, env) == []


def test_a_symlink_to_the_home_path_bound_for_the_public_repo_stops_the_sync(
    tmp_path: Path,
) -> None:
    """git stores a link's target as its content, so the target is what is published."""
    env, store, repo = _sync_env(tmp_path)
    (store / "views" / "最新 リンク").symlink_to(
        f"{env['HOME']}/.config/moltbook/views/view-2026-10-09.md"
    )
    proc = _sync(env)
    assert proc.returncode != 0
    assert "views/最新 リンク" in proc.stderr
    assert _commits(repo, env) == []


def test_a_tracked_file_gone_from_the_working_tree_does_not_break_the_gate(
    tmp_path: Path,
) -> None:
    """`git ls-files --cached` still lists a file rsync --delete removed; the gate
    must not try to read it, and the deletion is what the next commit publishes."""
    env, store, repo = _sync_env(tmp_path)
    assert _sync(env).returncode == 0
    (store / "views" / "view-2026-10-09.md").unlink()
    (store / "views" / "view-2026-10-16.md").write_text("# next week\n", encoding="utf-8")
    proc = _sync(env)
    assert proc.returncode == 0, proc.stderr
    assert len(_commits(repo, env)) == 2
    assert not (repo / "views" / "view-2026-10-09.md").exists()


def test_a_tracked_file_holding_the_home_path_stops_the_sync(tmp_path: Path) -> None:
    """The daily shape: a file published yesterday is rewritten with a leak."""
    env, store, repo = _sync_env(tmp_path)
    assert _sync(env).returncode == 0
    (store / "views" / "view-2026-10-09.md").write_text(
        f"# a view\nsee {env['HOME']}/.config/moltbook\n", encoding="utf-8"
    )
    proc = _sync(env)
    assert proc.returncode != 0
    assert "views/view-2026-10-09.md" in proc.stderr
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


# --- P0-03.2 / .3 / .4 / .6 / .7 / .16 ---------------------------------------

# Names that must never reach the public repo (the negative cases of P0-03.3).
# `_gc_trash/` is a directory and is exercised separately below.
WITHHELD_NAMES = (
    "knowledge.json.bak-dup-cleanup-20260718",
    ".run.lock",
    ".staged.lock",
    "credentials.json",
    "cloud.env",
    "orphan.abc123.tmp",
    ".last_insight",
)
GOVERNANCE = (
    ".gitignore",
    "README.md",
    "README.ja.md",
    "llms.txt",
    "LICENSE",
    "NOTICE",
    "CITATION.cff",
    ".zenodo.json",
    "graph.jsonld",
    "DATACARD.md",
)


def test_secrets_locks_bak_and_tmp_never_reach_the_public_transfer(tmp_path: Path) -> None:
    landed = _transfer(tmp_path, WITHHELD_NAMES)
    for name in WITHHELD_NAMES:
        assert name not in landed, f"{name} would be pushed to the PUBLIC data repo"
    assert "self_reflection.md" in landed


def test_gc_trash_stays_out_of_the_public_repo(tmp_path: Path) -> None:
    """D-P0-03-2 = A: retired-skill originals are not published (history keeps them)."""
    env, store, repo = _sync_env(tmp_path)
    trash = store / "skills" / "_gc_trash" / "2026-07-10-clean-rewrite-originals"
    trash.mkdir(parents=True)
    (trash / "old-skill.md").write_text("# an original\n", encoding="utf-8")
    (store / "skills" / "kept.md").write_text("# kept\n", encoding="utf-8")
    proc = _sync(env)
    assert proc.returncode == 0, proc.stderr
    assert (repo / "skills" / "kept.md").is_file()
    assert not (repo / "skills" / "_gc_trash").exists()


def test_an_unknown_top_level_name_is_not_transferred_and_is_named(tmp_path: Path) -> None:
    env, store, repo = _sync_env(tmp_path)
    (store / "foo.json").write_text("{}\n", encoding="utf-8")
    (store / "newdir").mkdir()
    (store / "newdir" / "x.md").write_text("x\n", encoding="utf-8")
    proc = _sync(env)
    assert proc.returncode == 0, proc.stderr
    assert not (repo / "foo.json").exists() and not (repo / "newdir").exists()
    assert "foo.json" in proc.stderr and "newdir" in proc.stderr
    assert (repo / "views" / "view-2026-10-09.md").is_file()


def test_known_withheld_top_level_names_are_not_reported(tmp_path: Path) -> None:
    env, store, _repo = _sync_env(tmp_path)
    (store / "logs").mkdir()
    (store / "agents.json").write_text("{}\n", encoding="utf-8")
    proc = _sync(env)
    assert proc.returncode == 0, proc.stderr
    assert "NOTE: not published" not in proc.stderr


def _git_in(repo: Path, env: dict[str, str], *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], env=env, capture_output=True, text=True, check=True
    ).stdout


def test_withheld_files_already_in_the_repo_are_retracted(tmp_path: Path) -> None:
    """`--exclude` shields the receiver from `--delete`; the retraction step is the cure."""
    env, _store, repo = _sync_env(tmp_path)
    for name in (".DS_Store", "x.bak", "reports/.DS_Store"):
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text("stand-in\n", encoding="utf-8")
    (repo / "skills").mkdir()
    (repo / "skills" / "_gc_trash").mkdir()
    (repo / "skills" / "_gc_trash" / "old.md").write_text("old\n", encoding="utf-8")
    _git_in(repo, env, "add", "-A")
    _git_in(repo, env, "commit", "-qm", "seed")
    proc = _sync(env)
    assert proc.returncode == 0, proc.stderr
    tracked = set(_git_in(repo, env, "ls-files").splitlines())
    assert not any(n.endswith((".DS_Store", ".bak")) or "_gc_trash" in n for n in tracked), tracked
    assert not (repo / "skills" / "_gc_trash").exists()


def test_retired_patch_proposals_and_ledger_watch_leave_the_public_repo(tmp_path: Path) -> None:
    """D-P3-05-4 = A (`patches/` is framework code, not data) and ADR-0095 (ledger-watch retired).

    The home still holds both, so the exclusion has to stop the copy and the
    retraction has to remove the copy the data repo already carries; the
    hand-kept `reports/analysis/README.md` and a weekly document published
    earlier beside them stay.
    """
    env, store, repo = _sync_env(tmp_path)
    for root in (store, repo):
        patch = (
            root / "reports" / "analysis" / "patches" / "weekly-2026-08-21" / "code" / "F1.1.patch"
        )
        patch.parent.mkdir(parents=True, exist_ok=True)
        patch.write_text("--- a/x\n+++ b/x\n", encoding="utf-8")
        watch = root / "pipeline" / "ledger-watch" / "ledger-watch-2026-08-14.json"
        watch.parent.mkdir(parents=True, exist_ok=True)
        watch.write_text("{}\n", encoding="utf-8")
    (repo / "reports" / "analysis" / "README.md").write_text("formats\n", encoding="utf-8")
    (repo / "reports" / "analysis" / "weekly-2026-08-21.md").write_text(
        "# published earlier\n", encoding="utf-8"
    )
    _git_in(repo, env, "add", "-A")
    _git_in(repo, env, "commit", "-qm", "seed")
    proc = _sync(env)
    assert proc.returncode == 0, proc.stderr
    tracked = set(_git_in(repo, env, "ls-files").splitlines())
    assert not any("/patches/" in n or "ledger-watch" in n for n in tracked), tracked
    assert "reports/analysis/README.md" in tracked
    assert "reports/analysis/weekly-2026-08-21.md" in tracked


def test_governance_files_and_knowledge_json_survive_a_sync(tmp_path: Path) -> None:
    """The retraction must never touch the 10 receiver-owned names or knowledge.json."""
    env, _store, repo = _sync_env(tmp_path)
    for name in GOVERNANCE:
        (repo / name).write_text(f"hand-kept {name}\n", encoding="utf-8")
    _git_in(repo, env, "add", "-A")
    _git_in(repo, env, "commit", "-qm", "seed")
    proc = _sync(env)
    assert proc.returncode == 0, proc.stderr
    for name in (*GOVERNANCE, "knowledge.json"):
        assert (repo / name).is_file(), f"{name} was removed by the sync"
    assert (repo / "README.md").read_text(encoding="utf-8") == "hand-kept README.md\n"


def test_the_rsync_version_line_is_in_the_commit_body(tmp_path: Path) -> None:
    env, _store, repo = _sync_env(tmp_path)
    assert _sync(env).returncode == 0
    body = _git_in(repo, env, "log", "-1", "--format=%b")
    # The counts summary (P0-06.4) may come first; the rsync line is its own paragraph.
    rsync_lines = [ln for ln in body.splitlines() if ln.startswith("rsync:")]
    assert rsync_lines and "version" in rsync_lines[0]


def test_an_unusable_rsync_bin_stops_the_sync(tmp_path: Path) -> None:
    env, _store, repo = _sync_env(tmp_path)
    proc = _sync({**env, "RSYNC_BIN": str(tmp_path / "no-such-rsync")})
    assert proc.returncode != 0
    assert "ERROR:" in proc.stderr and "RSYNC_BIN" in proc.stderr
    assert _commits(repo, env) == []


def test_a_secret_shaped_value_stops_the_sync_and_is_not_printed(tmp_path: Path) -> None:
    env, store, repo = _sync_env(tmp_path)
    secret = "sk-" + "a1B2c3D4e5" * 3
    (store / "views" / "leaky.md").write_text(f"token {secret}\n", encoding="utf-8")
    proc = _sync(env)
    assert proc.returncode != 0
    assert "ERROR:" in proc.stderr and "views/leaky.md" in proc.stderr
    assert secret not in proc.stderr + proc.stdout
    assert _commits(repo, env) == []
    assert _git_in(repo, env, "diff", "--cached", "--name-only") == ""  # nothing left staged


def test_the_words_api_key_and_bearer_do_not_stop_the_sync(tmp_path: Path) -> None:
    """Other agents' text contains them; the patterns are value shapes only."""
    env, store, repo = _sync_env(tmp_path)
    (store / "views" / "talk.md").write_text(
        "an api_key is sent as Bearer token, said a peer\n", encoding="utf-8"
    )
    proc = _sync(env)
    assert proc.returncode == 0, proc.stderr
    assert len(_commits(repo, env)) == 1


def _with_origin(tmp_path: Path, env: dict[str, str], store: Path, repo: Path) -> Path:
    """Give the data repo a bare origin it tracks, holding one seed commit."""
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True, env=env)
    _git_in(repo, env, "checkout", "-q", "-B", "main")
    _git_in(repo, env, "remote", "add", "origin", str(bare))
    _git_in(repo, env, "commit", "-q", "--allow-empty", "-m", "seed")
    _git_in(repo, env, "push", "-q", "-u", "origin", "main")
    return bare


def test_a_remote_only_commit_survives_the_sync_and_the_sync_fails(tmp_path: Path) -> None:
    env, store, repo = _sync_env(tmp_path)
    bare = _with_origin(tmp_path, env, store, repo)
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(bare), str(other)], check=True, env=env)
    (other / "NOTICE").write_text("edited on the remote\n", encoding="utf-8")
    _git_in(other, env, "add", "-A")
    _git_in(other, env, "commit", "-qm", "remote-only commit")
    _git_in(other, env, "push", "-q", "origin", "main")
    (store / "views" / "view-2026-10-16.md").write_text("# next week\n", encoding="utf-8")
    proc = _sync(env)
    assert proc.returncode != 0
    assert "ERROR:" in proc.stderr and "commits this checkout does not" in proc.stderr
    remote_log = subprocess.run(
        ["git", "-C", str(bare), "log", "--format=%s", "main"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "remote-only commit" in remote_log
    assert "sync: " not in remote_log.splitlines()[0]  # our commit was not forced over it
    # No local commit either, so the watchdog's "today's sync: commit" row goes red.
    assert not any(c.startswith("sync: ") for c in _commits(repo, env))


def test_a_fast_forward_sync_still_pushes(tmp_path: Path) -> None:
    env, store, repo = _sync_env(tmp_path)
    bare = _with_origin(tmp_path, env, store, repo)
    (store / "views" / "view-2026-10-16.md").write_text("# next week\n", encoding="utf-8")
    proc = _sync(env)
    assert proc.returncode == 0, proc.stderr
    remote_head = subprocess.run(
        ["git", "-C", str(bare), "log", "-1", "--format=%s", "main"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert remote_head.startswith("sync: ")


def test_only_openrsync_present_degrades_to_a_warning_and_still_syncs(tmp_path: Path) -> None:
    """A Mac without Homebrew rsync must not lose its daily sync (rsync 3.x is preferred, not required)."""
    import os
    import shutil

    if any(Path(p).exists() for p in ("/opt/homebrew/bin/rsync", "/usr/local/bin/rsync")):
        pytest.skip("a preferred rsync exists at a fixed path on this machine")
    real = shutil.which("rsync")
    if not real:
        pytest.skip("no rsync to wrap")
    env, _store, repo = _sync_env(tmp_path)
    stub = tmp_path / "stub-bin"
    stub.mkdir()
    (stub / "rsync").write_text(
        '#!/bin/sh\n[ "$1" = "--version" ] && { echo "openrsync: protocol version 29"; exit 0; }\n'
        f'exec "{real}" "$@"\n',
        encoding="utf-8",
    )
    (stub / "rsync").chmod(0o755)
    proc = _sync({**env, "PATH": f"{stub}:{os.environ['PATH']}"})
    assert proc.returncode == 0, proc.stderr
    assert "WARNING: no rsync 3.x" in proc.stderr
    assert len(_commits(repo, env)) == 1


def test_rejected_bodies_stay_out_of_the_public_transfer(tmp_path: Path) -> None:
    """P1-12.2: the kept text of rejected candidates is not published from here.

    Publishing it is a separate decision (P2-05); until that is taken the
    directory must never ride the sync, whatever the file is named, and
    wherever it sits (top level, or under an allowlisted directory).
    """
    env, store, repo = _sync_env(tmp_path)
    for parent in (store, store / "skills"):
        (parent / ".rejected").mkdir(parents=True)
        (parent / ".rejected" / "20261024T000000Z-0123456789abcdef.md").write_text(
            "# no\n", encoding="utf-8"
        )
    (store / "views").mkdir(exist_ok=True)
    (store / "views" / "self_reflection.md").write_text("# a view\n", encoding="utf-8")
    proc = _sync(env)
    assert proc.returncode == 0, proc.stderr
    landed = {
        p.relative_to(repo).as_posix()
        for p in repo.rglob("*")
        if p.is_file() and ".git" not in p.relative_to(repo).parts
    }
    assert not any(".rejected" in name for name in landed), landed
    assert "views/self_reflection.md" in landed


def test_a_failed_push_is_an_error_and_a_nonzero_exit(tmp_path: Path) -> None:
    """P2-04.2: the sync used to say WARNING and exit 0, so launchd never saw it."""
    env, store, repo = _sync_env(tmp_path)
    bare = _with_origin(tmp_path, env, store, repo)
    hook = bare / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    (store / "views" / "view-2026-10-16.md").write_text("# next week\n", encoding="utf-8")
    proc = _sync(env)
    assert proc.returncode == 1
    assert "ERROR: push failed" in proc.stderr
    assert "WARNING: push failed" not in proc.stderr


def test_the_regime_table_is_copied_from_this_repo_not_mirrored(tmp_path: Path) -> None:
    """pipeline/ is an rsync --delete mirror of MOLTBOOK_HOME, so the boundary table
    (P3-02.1) is copied in from docs/evidence/regimes/ after the rsync. A stale
    copy sitting in the store must not win, and a second sync leaves no new commit."""
    env, store, repo = _sync_env(tmp_path)
    (store / "pipeline").mkdir(parents=True, exist_ok=True)
    (store / "pipeline" / "regimes.json").write_text('{"stale": true}\n', encoding="utf-8")
    source = SCRIPT.parent.parent / "docs" / "evidence" / "regimes" / "regimes.json"
    proc = _sync(env)
    assert proc.returncode == 0, proc.stderr
    assert (repo / "pipeline" / "regimes.json").read_bytes() == source.read_bytes()
    first = _commits(repo, env)
    assert _sync(env).returncode == 0
    assert _commits(repo, env) == first


def test_moltbook_data_repo_points_the_sync_at_another_clone(tmp_path: Path) -> None:
    """P2-03.5: the owner's `$HOME/MyAI_Lab/...` layout is only the default."""
    env, _store, default_repo = _sync_env(tmp_path)
    other = tmp_path / "elsewhere" / "my-data"
    other.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(other)], check=True, env=env)
    env["MOLTBOOK_DATA_REPO"] = str(other)
    proc = _sync(env)
    assert proc.returncode == 0, proc.stderr
    assert _commits(other, env), (
        "the sync committed nothing to the repo named by MOLTBOOK_DATA_REPO"
    )
    assert not _commits(default_repo, env), (
        "the default repo was used although the variable was set"
    )


def test_a_missing_data_repo_names_the_variable_that_would_fix_it(tmp_path: Path) -> None:
    env, _store, _default = _sync_env(tmp_path)
    env["MOLTBOOK_DATA_REPO"] = str(tmp_path / "no-such-repo")
    proc = _sync(env)
    assert proc.returncode != 0
    assert str(tmp_path / "no-such-repo") in proc.stderr


# --- history/ and takedown file: entries (2026-10-24, ADR-0010 / ADR-0127) ---


def test_identity_history_is_published(tmp_path: Path) -> None:
    env, store, repo = _sync_env(tmp_path)
    (store / "history" / "identity").mkdir(parents=True)
    (store / "history" / "identity" / "20261024T000000Z-abcdef123456.md").write_text(
        "an adopted identity version\n", encoding="utf-8"
    )
    proc = _sync(env)
    assert proc.returncode == 0, proc.stderr
    assert (repo / "history" / "identity" / "20261024T000000Z-abcdef123456.md").is_file()
    assert "not on the allowlist: history" not in proc.stderr


def test_a_takedown_file_entry_is_not_copied_and_an_old_copy_is_withdrawn(
    tmp_path: Path,
) -> None:
    """A path the daily run sends: the exclusion is what keeps the home's copy
    from coming back. A document under reports/analysis/ is not sent at all;
    its takedown case is in the P2-05.1 section below."""
    env, store, repo = _sync_env(tmp_path)
    (store / "views" / "view-2026-10-02.md").write_text("# withdrawn later\n", encoding="utf-8")
    assert _sync(env).returncode == 0
    assert (repo / "views" / "view-2026-10-02.md").is_file()
    (store / "takedown-suppressions.txt").write_text(
        "# private list\npost:abcdef12\nfile:views/view-2026-10-02.md\n",
        encoding="utf-8",
    )
    (store / "views" / "view-2026-10-03.md").write_text("# a new view\n", encoding="utf-8")
    proc = _sync(env)
    assert proc.returncode == 0, proc.stderr
    assert not (repo / "views" / "view-2026-10-02.md").exists()
    assert (store / "views" / "view-2026-10-02.md").is_file()  # still at home, not copied
    assert (repo / "views" / "view-2026-10-09.md").is_file()
    tracked = set(_git_in(repo, env, "ls-files").splitlines())
    assert "views/view-2026-10-02.md" not in tracked
    assert "takedown-suppressions.txt" not in tracked  # the private list stays home
    assert "takedown: withdrew views/view-2026-10-02.md" in proc.stdout
    assert "not on the allowlist: takedown-suppressions.txt" not in proc.stderr


@pytest.mark.parametrize(
    "line",
    [
        "bogus-line",
        "file:/etc/passwd",
        "file:reports/../identity.md",
        "file:reports/*.md",
        "file:.git/config",
        "file:NOTICE",
    ],
)
def test_an_unusable_takedown_line_stops_the_sync_before_anything_is_copied(
    tmp_path: Path, line: str
) -> None:
    env, store, repo = _sync_env(tmp_path)
    (store / "takedown-suppressions.txt").write_text(line + "\n", encoding="utf-8")
    proc = _sync(env)
    assert proc.returncode != 0
    assert "ADR-0127" in proc.stderr
    assert not (repo / "reports").exists()
    assert _commits(repo, env) == []


# --- ADR-0010 amendment 2026-10-31: no other agent's text in the public reports ---


def _ca_bin(tmp_path: Path) -> Path:
    """A stand-in for the venv's ``contemplative-agent`` that runs this checkout."""
    import stat
    import sys

    stub = tmp_path / "bin" / "contemplative-agent"
    stub.parent.mkdir(exist_ok=True)
    stub.write_text(
        f'#!/bin/sh\nPYTHONPATH="{REPO_ROOT / "src"}" exec "{sys.executable}" '
        '-m contemplative_agent "$@"\n',
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    return stub


def _episode(store: Path, date: str, their_text: str) -> None:
    import json

    episodes = store / "logs" / "episodes"
    episodes.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": f"{date}T01:00:00+00:00",
        "type": "activity",
        "data": {
            "action": "comment",
            "post_id": "p1",
            "content": "my reply",
            "original_post": their_text,
        },
    }
    (episodes / f"{date}.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")


def test_the_public_comment_report_carries_no_context_text(tmp_path: Path) -> None:
    env, store, repo = _sync_env(tmp_path)
    _episode(store, "2026-10-30", "THEIR-POST-TEXT")
    private = store / "reports" / "comment-reports"
    private.mkdir(parents=True)
    (private / "comment-report-2026-10-30.md").write_text(
        "**Context:**\nTHEIR-POST-TEXT\n", encoding="utf-8"
    )
    proc = _sync({**env, "PATH": f"{_ca_bin(tmp_path).parent}:{env['PATH']}"})
    assert proc.returncode == 0, proc.stderr
    public = (repo / "reports" / "comment-reports" / "comment-report-2026-10-30.md").read_text(
        encoding="utf-8"
    )
    assert "THEIR-POST-TEXT" not in public
    assert "my reply" in public
    assert "omitted in the public copy" in public
    # the private report is the weekly chain's input and keeps the section
    assert "THEIR-POST-TEXT" in (private / "comment-report-2026-10-30.md").read_text(
        encoding="utf-8"
    )


def test_an_older_public_copy_with_context_is_withdrawn(tmp_path: Path) -> None:
    env, store, repo = _sync_env(tmp_path)
    _episode(store, "2026-10-30", "THEIR-POST-TEXT")
    stale = repo / "reports" / "comment-reports" / "comment-report-2026-03-07.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("**Context:**\nOLD-THEIR-TEXT\n", encoding="utf-8")
    proc = _sync({**env, "PATH": f"{_ca_bin(tmp_path).parent}:{env['PATH']}"})
    assert proc.returncode == 0, proc.stderr
    assert not stale.exists()


def test_a_failed_render_stops_the_sync_before_anything_is_committed(tmp_path: Path) -> None:
    import stat

    env, store, repo = _sync_env(tmp_path)
    _episode(store, "2026-10-30", "THEIR-POST-TEXT")
    broken = tmp_path / "broken-bin" / "contemplative-agent"
    broken.parent.mkdir()
    broken.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    broken.chmod(broken.stat().st_mode | stat.S_IXUSR)
    proc = _sync({**env, "PATH": f"{broken.parent}:{env['PATH']}"})
    assert proc.returncode != 0
    assert _commits(repo, env) == []


def test_a_takedown_of_a_comment_report_holds_after_the_render(tmp_path: Path) -> None:
    env, store, repo = _sync_env(tmp_path)
    _episode(store, "2026-10-30", "THEIR-POST-TEXT")
    (store / "takedown-suppressions.txt").write_text(
        "file:reports/comment-reports/comment-report-2026-10-30.md\n", encoding="utf-8"
    )
    proc = _sync({**env, "PATH": f"{_ca_bin(tmp_path).parent}:{env['PATH']}"})
    assert proc.returncode == 0, proc.stderr
    assert not (repo / "reports" / "comment-reports" / "comment-report-2026-10-30.md").exists()


def test_no_episode_logs_keeps_the_public_reports_and_warns(tmp_path: Path) -> None:
    env, store, repo = _sync_env(tmp_path)
    kept = repo / "reports" / "comment-reports" / "comment-report-2026-10-29.md"
    kept.parent.mkdir(parents=True)
    kept.write_text("**Context:** omitted in the public copy.\n", encoding="utf-8")
    proc = _sync({**env, "PATH": f"{_ca_bin(tmp_path).parent}:{env['PATH']}"})
    assert proc.returncode == 0, proc.stderr
    assert kept.exists()
    assert "logs/episodes not found" in proc.stderr


def test_a_context_line_with_trailing_space_still_stops_the_sync(tmp_path: Path) -> None:
    env, store, repo = _sync_env(tmp_path)
    left = repo / "reports" / "comment-reports" / "comment-report-2026-10-29.md"
    left.parent.mkdir(parents=True)
    left.write_text("**Context:**\r\nTHEIR-POST-TEXT\r\n", encoding="utf-8", newline="")
    proc = _sync({**env, "PATH": f"{_ca_bin(tmp_path).parent}:{env['PATH']}"})
    assert proc.returncode != 0
    assert "still holds a Context section" in proc.stderr


# --- P2-05.1: the unattended sync leaves reports/analysis/ to the Saturday gate ---
#
# ADR-0010 amendment 2026-10-31 (two layers of public output): documents the
# unattended `claude -p` session writes are published only after the owner has
# read them. The daily sync therefore adds nothing to the data repo's
# `reports/analysis/`, rewrites nothing there and deletes nothing there (what
# is already public stays; withdrawing it is the takedown route). The owner
# names one weekly document with `--promote` at weekly-gate Step 6d, and that run
# copies only it, then goes through every pre-commit gate the daily run does.
# These run real transfers: removing the exclusion makes them fail.

ANALYSIS = Path("reports") / "analysis"


def _analysis_files(repo: Path) -> dict[str, str]:
    root = repo / ANALYSIS
    if not root.is_dir():
        return {}
    return {
        p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
        for p in root.rglob("*")
        if p.is_file()
    }


def _write_weekly(store: Path, name: str, text: str) -> None:
    (store / ANALYSIS / name).write_text(text, encoding="utf-8")


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _promote(
    env: dict[str, str], store: Path, name: str, *extra: str
) -> subprocess.CompletedProcess:
    """Promote *name* pinned to the bytes the owner read: the home file's sha256 now."""
    return _sync(env, "--promote", name, "--sha256", _sha256(store / ANALYSIS / name), *extra)


def test_the_unattended_sync_adds_nothing_to_reports_analysis(tmp_path: Path) -> None:
    env, store, repo = _sync_env(tmp_path)
    _write_weekly(store, "weekly-2026-10-09-findings.md", "# F1 / F2 / F3\n")
    (store / ANALYSIS / "observation-ledger.jsonl").write_text("{}\n", encoding="utf-8")
    (store / "views").mkdir(exist_ok=True)
    (store / "views" / "self_reflection.md").write_text("# a view\n", encoding="utf-8")
    proc = _sync(env)
    assert proc.returncode == 0, proc.stderr
    assert _analysis_files(repo) == {}
    tracked = set(_git_in(repo, env, "ls-files").splitlines())
    assert not any(n.startswith("reports/analysis/") for n in tracked), tracked
    assert "views/self_reflection.md" in tracked  # the machine layer still goes out


def test_the_unattended_sync_neither_rewrites_nor_deletes_published_analysis(
    tmp_path: Path,
) -> None:
    """What is public stays as it is: `--delete` must not reach an excluded path."""
    env, store, repo = _sync_env(tmp_path)
    published = {
        "weekly-2026-10-02.md": "# promoted earlier, gone from the home since\n",
        "weekly-2026-10-09.md": "# the version the owner read\n",
        "README.md": "formats\n",
    }
    (repo / ANALYSIS).mkdir(parents=True)
    for name, text in published.items():
        (repo / ANALYSIS / name).write_text(text, encoding="utf-8")
    _git_in(repo, env, "add", "-A")
    _git_in(repo, env, "commit", "-qm", "seed")
    # The home's copy of 10-09 has moved on; 10-02 is no longer in the home.
    _write_weekly(store, "weekly-2026-10-09.md", "# rewritten by a later run\n")
    _write_weekly(store, "weekly-2026-10-16.md", "# next week\n")
    proc = _sync(env)
    assert proc.returncode == 0, proc.stderr
    assert _analysis_files(repo) == published
    assert _git_in(repo, env, "status", "--porcelain", "--", "reports/analysis") == ""
    assert (
        _git_in(repo, env, "diff", "HEAD~1", "HEAD", "--name-only", "--", "reports/analysis") == ""
    )


def test_published_analysis_survives_a_home_without_a_reports_directory(tmp_path: Path) -> None:
    """The directory-level case of `--delete`: nothing on the sending side at all."""
    import shutil

    env, store, repo = _sync_env(tmp_path)
    shutil.rmtree(store / "reports")
    (repo / ANALYSIS).mkdir(parents=True)
    (repo / ANALYSIS / "weekly-2026-10-02.md").write_text("# public\n", encoding="utf-8")
    _git_in(repo, env, "add", "-A")
    _git_in(repo, env, "commit", "-qm", "seed")
    proc = _sync(env)
    assert proc.returncode == 0, proc.stderr
    assert _analysis_files(repo) == {"weekly-2026-10-02.md": "# public\n"}


def test_promote_publishes_the_one_named_document_and_nothing_else(tmp_path: Path) -> None:
    env, store, repo = _sync_env(tmp_path)
    _write_weekly(store, "weekly-2026-10-16.md", "# the week the owner read\n")
    _write_weekly(store, "weekly-2026-10-16-findings.md", "# not named\n")
    (store / ANALYSIS / "observation-ledger.jsonl").write_text("{}\n", encoding="utf-8")
    proc = _promote(env, store, "weekly-2026-10-16.md")
    assert proc.returncode == 0, proc.stderr
    assert _analysis_files(repo) == {"weekly-2026-10-16.md": "# the week the owner read\n"}
    tracked = set(_git_in(repo, env, "ls-files").splitlines())
    assert "reports/analysis/weekly-2026-10-16.md" in tracked
    commits = _commits(repo, env)
    assert len(commits) == 1 and commits[0].startswith("sync: ")  # the watchdog's subject
    body = _git_in(repo, env, "log", "-1", "--format=%b")
    assert "promote: reports/analysis/weekly-2026-10-16.md" in body.splitlines()
    # The next unattended run neither withdraws it nor adds the others.
    assert _sync(env).returncode == 0
    assert _analysis_files(repo) == {"weekly-2026-10-16.md": "# the week the owner read\n"}


def test_promote_takes_a_findings_document_by_name(tmp_path: Path) -> None:
    env, store, repo = _sync_env(tmp_path)
    _write_weekly(store, "weekly-2026-10-09-findings.md", "# findings\n")
    proc = _promote(env, store, "weekly-2026-10-09-findings.md")
    assert proc.returncode == 0, proc.stderr
    assert set(_analysis_files(repo)) == {"weekly-2026-10-09-findings.md"}


def test_promote_replaces_an_earlier_published_copy_of_the_same_document(tmp_path: Path) -> None:
    env, store, repo = _sync_env(tmp_path)
    (repo / ANALYSIS).mkdir(parents=True)
    (repo / ANALYSIS / "weekly-2026-10-09.md").write_text("# old\n", encoding="utf-8")
    (repo / ANALYSIS / "weekly-2026-10-02.md").write_text("# untouched\n", encoding="utf-8")
    _git_in(repo, env, "add", "-A")
    _git_in(repo, env, "commit", "-qm", "seed")
    proc = _promote(env, store, "weekly-2026-10-09.md")
    assert proc.returncode == 0, proc.stderr
    assert _analysis_files(repo) == {
        "weekly-2026-10-09.md": "# a clean report\n",
        "weekly-2026-10-02.md": "# untouched\n",
    }


@pytest.mark.parametrize(
    "args",
    [
        ("--promote",),
        ("--promote", ""),
        ("--promote", "../../identity.md"),
        ("--promote", "reports/analysis/weekly-2026-10-09.md"),
        ("--promote", "observation-ledger.jsonl"),
        ("--promote", "weekly-2026-10-*.md"),
        ("--promote", "weekly-2026-10-23.md"),  # not in the home
        ("--promote", "weekly-2026-10-09.md", "--promote", "weekly-2026-10-16.md"),
        ("--bogus",),
        # 4a: the bytes the owner read are pinned by their sha256 (bounce 1)
        ("--promote", "weekly-2026-10-16.md"),  # no --sha256
        ("--promote", "weekly-2026-10-16.md", "--sha256"),
        ("--promote", "weekly-2026-10-16.md", "--sha256", "not-a-sha256"),
        ("--promote", "weekly-2026-10-16.md", "--sha256", "0" * 64),  # another document's
        ("--sha256", "0" * 64),  # a hash with nothing to promote
    ],
)
def test_an_unusable_promote_request_stops_before_anything_is_copied(
    tmp_path: Path, args: tuple[str, ...]
) -> None:
    env, store, repo = _sync_env(tmp_path)
    _write_weekly(store, "weekly-2026-10-16.md", "# next week\n")
    (store / ANALYSIS / "observation-ledger.jsonl").write_text("{}\n", encoding="utf-8")
    proc = _sync(env, *args)
    assert proc.returncode != 0
    assert "ERROR:" in proc.stderr
    assert not (repo / "reports").exists() and not (repo / "knowledge.json").exists()
    assert _commits(repo, env) == []


def test_promote_refuses_a_symlink(tmp_path: Path) -> None:
    """A link is published as its target path, or followed to a file nobody read."""
    env, store, repo = _sync_env(tmp_path)
    (store / "credentials.json").write_text('{"api_key": "x"}\n', encoding="utf-8")
    (store / ANALYSIS / "weekly-2026-10-23.md").symlink_to(store / "credentials.json")
    proc = _sync(
        env, "--promote", "weekly-2026-10-23.md", "--sha256", _sha256(store / "credentials.json")
    )
    assert proc.returncode != 0
    assert "ERROR:" in proc.stderr
    assert _analysis_files(repo) == {}
    assert _commits(repo, env) == []


@pytest.mark.parametrize(
    "entry", ["file:reports/analysis/weekly-2026-10-09.md", "file:reports/analysis", "file:reports"]
)
def test_promote_refuses_a_document_under_a_takedown(tmp_path: Path, entry: str) -> None:
    """A withdrawal outranks a promote: say so instead of copying and then removing it."""
    env, store, repo = _sync_env(tmp_path)
    (store / "takedown-suppressions.txt").write_text(entry + "\n", encoding="utf-8")
    proc = _promote(env, store, "weekly-2026-10-09.md")
    assert proc.returncode != 0
    assert "takedown" in proc.stderr
    assert _analysis_files(repo) == {}
    assert _commits(repo, env) == []


def test_a_promoted_document_goes_through_the_home_path_gate(tmp_path: Path) -> None:
    env, store, repo = _sync_env(tmp_path)
    _write_weekly(store, "weekly-2026-10-16.md", f"see {env['HOME']}/.config/moltbook\n")
    proc = _promote(env, store, "weekly-2026-10-16.md")
    assert proc.returncode != 0
    assert "reports/analysis/weekly-2026-10-16.md" in proc.stderr
    assert _commits(repo, env) == []


def test_a_promoted_document_goes_through_the_secret_scan(tmp_path: Path) -> None:
    env, store, repo = _sync_env(tmp_path)
    secret = "sk-" + "a1B2c3D4e5" * 3
    _write_weekly(store, "weekly-2026-10-16.md", f"token {secret}\n")
    proc = _promote(env, store, "weekly-2026-10-16.md")
    assert proc.returncode != 0
    assert "reports/analysis/weekly-2026-10-16.md" in proc.stderr
    assert secret not in proc.stderr + proc.stdout
    assert _commits(repo, env) == []


def test_a_takedown_withdraws_an_already_published_analysis_document(tmp_path: Path) -> None:
    """The exclusion keeps what is public; withdrawing it stays the takedown's job."""
    env, store, repo = _sync_env(tmp_path)
    (repo / ANALYSIS).mkdir(parents=True)
    for name in ("weekly-2026-10-02.md", "weekly-2026-10-09.md"):
        (repo / ANALYSIS / name).write_text(f"# {name}\n", encoding="utf-8")
    _git_in(repo, env, "add", "-A")
    _git_in(repo, env, "commit", "-qm", "seed")
    (store / "takedown-suppressions.txt").write_text(
        "file:reports/analysis/weekly-2026-10-02.md\n", encoding="utf-8"
    )
    proc = _sync(env)
    assert proc.returncode == 0, proc.stderr
    assert set(_analysis_files(repo)) == {"weekly-2026-10-09.md"}
    tracked = set(_git_in(repo, env, "ls-files").splitlines())
    assert "reports/analysis/weekly-2026-10-02.md" not in tracked


def test_the_interpreter_argument_still_works_beside_promote(tmp_path: Path) -> None:
    """`contemplative-agent sync-data` passes its interpreter as the one positional."""
    import sys

    env, store, repo = _sync_env(tmp_path)
    _episode(store, "2026-10-30", "THEIR-POST-TEXT")
    pythonpath = {**env, "PYTHONPATH": str(REPO_ROOT / "src")}
    proc = _promote(pythonpath, store, "weekly-2026-10-09.md", sys.executable)
    assert proc.returncode == 0, proc.stderr
    assert (repo / "reports" / "comment-reports" / "comment-report-2026-10-30.md").is_file()
    assert set(_analysis_files(repo)) == {"weekly-2026-10-09.md"}


SAMPLE_OMITTED = (
    "_Sample omitted from the public copy: it quotes other agents' posts "
    "(ADR-0010 amendment 2026-10-31)._"
)


@pytest.mark.parametrize(
    "heading", ["## Sample", "## Random Sample (deterministic control channel)"]
)
def test_a_promoted_report_drops_the_whole_sample_section(tmp_path: Path, heading: str) -> None:
    """Owner's decision (bounce 1): the Sample section quotes other agents' posts
    (scripts/weekly_random_sample.py), so the public copy drops it whole, whatever
    its labels look like, and says so in one line (D-P3-05-7 = A)."""
    env, store, repo = _sync_env(tmp_path)
    private_text = (
        "# Weekly 2026-10-16\n\n## Observations\n\nthe writer's prose stays\n\n"
        f"{heading}\n\n### Sample 1/2 — 2026-10-15 [someone]\n\n"
        "**context (UNTRUSTED):** THEIR-POST-TEXT in a variant label\n\n"
        "**Output (agent):** my reply, also inside the Sample\n\n"
        "> **Context:** QUOTED-THEIR-TEXT\n\n"
        "### Sample 2/2 — 2026-10-16 [other]\n\nMORE-SAMPLE-TEXT\n\n"
        "## Ledger\n\nthe ledger section stays\n"
    )
    _write_weekly(store, "weekly-2026-10-16.md", private_text)
    proc = _promote(env, store, "weekly-2026-10-16.md")
    assert proc.returncode == 0, proc.stderr
    public = (repo / ANALYSIS / "weekly-2026-10-16.md").read_text(encoding="utf-8")
    for gone in ("THEIR-POST-TEXT", "QUOTED-THEIR-TEXT", "MORE-SAMPLE-TEXT", "my reply", heading):
        assert gone not in public, gone
    assert public == (
        "# Weekly 2026-10-16\n\n## Observations\n\nthe writer's prose stays\n\n"
        f"{SAMPLE_OMITTED}\n\n## Ledger\n\nthe ledger section stays\n"
    )
    # the private document is the weekly chain's input and keeps the section
    assert (store / ANALYSIS / "weekly-2026-10-16.md").read_text(encoding="utf-8") == private_text


def test_a_sample_section_at_the_end_of_the_document_is_dropped_to_the_end(tmp_path: Path) -> None:
    env, store, repo = _sync_env(tmp_path)
    _write_weekly(
        store,
        "weekly-2026-10-16.md",
        "# Weekly\n\n## Notes\n\nkept\n\n## Sample\n\n### Sample 1/1\n\nLAST-TEXT\n",
    )
    proc = _promote(env, store, "weekly-2026-10-16.md")
    assert proc.returncode == 0, proc.stderr
    public = (repo / ANALYSIS / "weekly-2026-10-16.md").read_text(encoding="utf-8")
    assert public == f"# Weekly\n\n## Notes\n\nkept\n\n{SAMPLE_OMITTED}\n"


@pytest.mark.parametrize(
    "line",
    [
        "**Context (counterparty, untrusted):** THEIR-TEXT",
        "> **Context:** THEIR-TEXT",
        "**context (Untrusted):** THEIR-TEXT",
        "Context (counterparty) wrote THEIR-TEXT",
        "__Context:__ THEIR-TEXT",
        "**CONTEXT**: THEIR-TEXT",
    ],
)
def test_a_context_label_outside_the_sample_refuses_the_promote(tmp_path: Path, line: str) -> None:
    """Fail closed: a counterparty Context label left after the Sample is dropped
    means other agents' text in a place code did not put it; nothing is copied."""
    env, store, repo = _sync_env(tmp_path)
    _write_weekly(
        store,
        "weekly-2026-10-16.md",
        f"# Weekly\n\n## Observations\n\n{line}\n\n## Sample\n\nsample\n",
    )
    proc = _promote(env, store, "weekly-2026-10-16.md")
    assert proc.returncode != 0
    assert "CONTEXT_LABEL" in proc.stderr
    assert "THEIR-TEXT" not in proc.stderr + proc.stdout
    assert _analysis_files(repo) == {}
    assert _commits(repo, env) == []


def test_a_document_without_a_sample_section_is_published_byte_for_byte(tmp_path: Path) -> None:
    """No Sample, nothing changed: CRLF lines and a missing final newline survive."""
    env, store, repo = _sync_env(tmp_path)
    raw = b"# Weekly\r\n\r\n## Findings\r\n\r\nF1 stays as written, no final newline"
    (store / ANALYSIS / "weekly-2026-10-16-findings.md").write_bytes(raw)
    proc = _promote(env, store, "weekly-2026-10-16-findings.md")
    assert proc.returncode == 0, proc.stderr
    assert (repo / ANALYSIS / "weekly-2026-10-16-findings.md").read_bytes() == raw


def test_promote_refuses_a_document_changed_after_the_owner_read_it(tmp_path: Path) -> None:
    """4a: `--sha256` is the hash recorded when the owner approved at the gate."""
    env, store, repo = _sync_env(tmp_path)
    _write_weekly(store, "weekly-2026-10-16.md", "# the version the owner read\n")
    read_hash = _sha256(store / ANALYSIS / "weekly-2026-10-16.md")
    _write_weekly(store, "weekly-2026-10-16.md", "# rewritten by a re-run after the gate\n")
    proc = _sync(env, "--promote", "weekly-2026-10-16.md", "--sha256", read_hash)
    assert proc.returncode != 0
    assert "sha256" in proc.stderr
    assert _analysis_files(repo) == {}
    assert _commits(repo, env) == []


def test_promote_accepts_the_sha256_in_upper_case(tmp_path: Path) -> None:
    env, store, repo = _sync_env(tmp_path)
    digest = _sha256(store / ANALYSIS / "weekly-2026-10-09.md").upper()
    proc = _sync(env, "--promote", "weekly-2026-10-09.md", "--sha256", digest)
    assert proc.returncode == 0, proc.stderr
    assert set(_analysis_files(repo)) == {"weekly-2026-10-09.md"}


def test_a_document_swapped_after_its_check_is_not_what_gets_published(tmp_path: Path) -> None:
    """4b: check and copy the same bytes. A `python3` wrapper swaps the home document
    for a symlink right after the first interpreter call that names it, i.e. after
    the check; a run that copied the path again would publish the swapped-in file."""
    import shutil

    env, store, repo = _sync_env(tmp_path)
    src = store / ANALYSIS / "weekly-2026-10-16.md"
    _write_weekly(store, "weekly-2026-10-16.md", "# the version the owner read\n")
    digest = _sha256(src)
    secret = store / "credentials.json"
    secret.write_text("SWAPPED-IN-AFTER-THE-CHECK\n", encoding="utf-8")
    real = shutil.which("python3", path=env["PATH"])
    assert real
    stub = tmp_path / "swap-bin"
    stub.mkdir()
    (stub / "python3").write_text(
        "#!/bin/sh\n"
        f'"{real}" "$@"; rc=$?\n'
        'for a in "$@"; do\n'
        f'  if [ "$a" = "{src}" ] && [ ! -e "{tmp_path}/swapped" ]; then\n'
        f'    : > "{tmp_path}/swapped"; rm -f "{src}"; ln -s "{secret}" "{src}"\n'
        "  fi\n"
        "done\n"
        "exit $rc\n",
        encoding="utf-8",
    )
    (stub / "python3").chmod(0o755)
    proc = _sync(
        {**env, "PATH": f"{stub}:{env['PATH']}"},
        "--promote",
        "weekly-2026-10-16.md",
        "--sha256",
        digest,
    )
    assert (tmp_path / "swapped").exists(), "the wrapper never saw the document's path"
    published = _analysis_files(repo)
    assert all("SWAPPED-IN" not in text for text in published.values()), proc.stdout
    if proc.returncode == 0:
        assert published == {"weekly-2026-10-16.md": "# the version the owner read\n"}


# --- bounce 1, item 1: nothing is left in the data repo by a stopped promote ---


@pytest.mark.parametrize("leak", ["secret", "home-path"])
def test_a_stopped_promote_leaves_the_data_repo_clean(tmp_path: Path, leak: str) -> None:
    """The copy is built and checked outside the data repo; a stopped run leaves
    nothing there for the next unattended sync to commit."""
    env, store, repo = _sync_env(tmp_path)
    assert _sync(env).returncode == 0
    before = _commits(repo, env)
    text = (
        "token sk-" + "a1B2c3D4e5" * 3 + "\n"
        if leak == "secret"
        else f"see {env['HOME']}/.config/moltbook\n"
    )
    _write_weekly(store, "weekly-2026-10-16.md", text)
    proc = _promote(env, store, "weekly-2026-10-16.md")
    assert proc.returncode != 0
    assert "reports/analysis/weekly-2026-10-16.md" in proc.stderr
    assert _git_in(repo, env, "status", "--porcelain", "--untracked-files=all") == ""
    assert _commits(repo, env) == before
    # and the next unattended run publishes nothing under reports/analysis/
    assert _sync(env).returncode == 0
    assert _analysis_files(repo) == {}


@pytest.mark.parametrize("earlier", [None, "# the copy published before\n"])
def test_a_failure_after_the_copy_is_placed_leaves_nothing_behind(
    tmp_path: Path, earlier: str | None
) -> None:
    """The trap: a commit that fails after the copy went in restores what HEAD holds."""
    import shutil

    env, store, repo = _sync_env(tmp_path)
    if earlier is not None:
        (repo / ANALYSIS).mkdir(parents=True)
        (repo / ANALYSIS / "weekly-2026-10-09.md").write_text(earlier, encoding="utf-8")
        _git_in(repo, env, "add", "-A")
        _git_in(repo, env, "commit", "-qm", "seed")
    real_git = shutil.which("git", path=env["PATH"])
    assert real_git
    stub = tmp_path / "stub-bin"
    stub.mkdir()
    (stub / "git").write_text(
        "#!/bin/sh\n"
        'case "$1" in commit) echo "fatal: simulated commit failure" >&2; exit 1;; esac\n'
        f'exec "{real_git}" "$@"\n',
        encoding="utf-8",
    )
    (stub / "git").chmod(0o755)
    proc = _promote({**env, "PATH": f"{stub}:{env['PATH']}"}, store, "weekly-2026-10-09.md")
    assert proc.returncode != 0
    assert "simulated commit failure" in proc.stderr
    assert (
        _git_in(
            repo, env, "status", "--porcelain", "--untracked-files=all", "--", "reports/analysis"
        )
        == ""
    )
    if earlier is None:
        assert _analysis_files(repo) == {}
    else:
        assert _analysis_files(repo) == {"weekly-2026-10-09.md": earlier}


@pytest.mark.parametrize("change", ["untracked", "modified", "deleted"])
def test_a_stray_change_under_reports_analysis_stops_the_unattended_sync(
    tmp_path: Path, change: str
) -> None:
    """Fail closed: the unattended run neither commits nor deletes a change it did not make."""
    env, store, repo = _sync_env(tmp_path)
    (repo / ANALYSIS).mkdir(parents=True)
    (repo / ANALYSIS / "weekly-2026-10-02.md").write_text("# published\n", encoding="utf-8")
    _git_in(repo, env, "add", "-A")
    _git_in(repo, env, "commit", "-qm", "seed")
    if change == "untracked":
        stray = repo / ANALYSIS / "x.md"
        stray.write_text("# left by a stopped promote\n", encoding="utf-8")
        named = "reports/analysis/x.md"
    elif change == "modified":
        stray = repo / ANALYSIS / "weekly-2026-10-02.md"
        stray.write_text("# edited by hand\n", encoding="utf-8")
        named = "reports/analysis/weekly-2026-10-02.md"
    else:
        (repo / ANALYSIS / "weekly-2026-10-02.md").unlink()
        stray = None
        named = "reports/analysis/weekly-2026-10-02.md"
    status_before = _git_in(repo, env, "status", "--porcelain", "--untracked-files=all")
    proc = _sync(env)
    assert proc.returncode != 0
    assert "ERROR:" in proc.stderr and named in proc.stderr
    assert _commits(repo, env) == ["seed"]
    assert _git_in(repo, env, "status", "--porcelain", "--untracked-files=all") == status_before
    if stray is not None:
        assert stray.is_file()


# --- bounce 1, item 3: takedown name: / post: entries reach the promoted copy ---


@pytest.mark.parametrize(
    ("entry", "mention"),
    [
        ("name:Some Agent", "a reply to SOME AGENT about care"),
        ("post:1a2b3c4d", "see post 1a2b3c4d-5e6f-7a8b-9c0d-112233445566"),
        ("post:1a2b3c4d-5e6f-7a8b-9c0d-112233445566", "post 1a2b3c4d (short id)"),
    ],
)
def test_a_document_naming_a_taken_down_name_or_post_is_refused(
    tmp_path: Path, entry: str, mention: str
) -> None:
    env, store, repo = _sync_env(tmp_path)
    (store / "takedown-suppressions.txt").write_text(entry + "\n", encoding="utf-8")
    _write_weekly(store, "weekly-2026-10-16.md", f"# Weekly\n\n## Observations\n\n{mention}\n")
    proc = _promote(env, store, "weekly-2026-10-16.md")
    assert proc.returncode != 0
    assert "TAKEDOWN" in proc.stderr
    assert entry.split(":", 1)[1] not in proc.stderr  # the private list is not echoed
    assert _analysis_files(repo) == {}
    assert _commits(repo, env) == []


def test_a_name_that_is_only_part_of_a_word_does_not_refuse(tmp_path: Path) -> None:
    """Same rule as core.takedown: a listed name matches as a whole word only."""
    env, store, repo = _sync_env(tmp_path)
    (store / "takedown-suppressions.txt").write_text("name:care\n", encoding="utf-8")
    _write_weekly(store, "weekly-2026-10-16.md", "# Weekly\n\ncareful words, scarecrow\n")
    proc = _promote(env, store, "weekly-2026-10-16.md")
    assert proc.returncode == 0, proc.stderr


def test_a_taken_down_name_only_inside_the_dropped_sample_does_not_refuse(tmp_path: Path) -> None:
    """The match runs on the copy that would be published; the Sample is not in it."""
    env, store, repo = _sync_env(tmp_path)
    (store / "takedown-suppressions.txt").write_text("name:someone\n", encoding="utf-8")
    _write_weekly(
        store,
        "weekly-2026-10-16.md",
        "# Weekly\n\n## Sample\n\n### Sample 1/1 — [someone]\n\nx\n\n## Notes\n\nkept\n",
    )
    proc = _promote(env, store, "weekly-2026-10-16.md")
    assert proc.returncode == 0, proc.stderr
    assert "someone" not in (repo / ANALYSIS / "weekly-2026-10-16.md").read_text(encoding="utf-8")


def test_the_promote_takedown_matcher_agrees_with_core_takedown() -> None:
    """The stdlib mirror in promote_public_copy.py is pinned to core.takedown."""
    import importlib.util
    import sys

    sys.path.insert(0, str(REPO_ROOT / "src"))
    try:
        from contemplative_agent.core.takedown import parse
    finally:
        sys.path.pop(0)
    spec = importlib.util.spec_from_file_location(
        "promote_public_copy", REPO_ROOT / "scripts" / "promote_public_copy.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # @dataclass resolves the module by name
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.modules.pop(spec.name, None)
    listing = "name:Some Agent\nname:Ünïcode\npost:1a2b3c4d\npost:ffffeeee-0000-1111\n"
    core = parse(listing)
    mine = mod.parse_suppressions(listing)
    for text in (
        "some agent said",
        "awesome agent said",
        "Some-Agent",
        "ünïcode!",
        "x ünïcodes",
        "id 1a2b3c4d-aaaa",
        "id 1a2b3c4",
        "id ffffeeee",
        "id ffffeeee-0000-1111-2222",
        "id fffeeee0",
        "nothing here",
    ):
        expected = core.text_names_withdrawn(text) or any(
            core.post_withdrawn(tok) for tok in mod.id_tokens(text)
        )
        assert mod.takedown_hits(text, mine) == expected, text


# --- bounce 1, item 4c: the exclusion holds for a non-directory at that path ---


@pytest.mark.parametrize("kind", ["file", "symlink"])
def test_a_non_directory_at_reports_analysis_is_not_transferred(tmp_path: Path, kind: str) -> None:
    import shutil

    env, store, repo = _sync_env(tmp_path)
    shutil.rmtree(store / ANALYSIS)
    if kind == "file":
        (store / ANALYSIS).write_text("# not a directory\n", encoding="utf-8")
    else:
        (store / ANALYSIS).symlink_to(store / "views")
    proc = _sync(env)
    assert proc.returncode == 0, proc.stderr
    assert not (repo / ANALYSIS).exists() and not (repo / ANALYSIS).is_symlink()


@pytest.mark.parametrize("cause", ["takedown", "withheld"])
def test_a_deletion_the_sync_itself_makes_does_not_stop_the_next_run(
    tmp_path: Path, cause: str
) -> None:
    """The retraction steps delete under reports/analysis/ too (a takedown `file:`
    entry, a withheld name such as `patches/`). If that run stopped before its
    commit, the deletion is left in the tree; the next run re-applies it and
    commits it instead of treating it as a stray change."""
    env, store, repo = _sync_env(tmp_path)
    rel = (
        "reports/analysis/weekly-2026-10-02.md"
        if cause == "takedown"
        else "reports/analysis/patches/weekly-2026-08-21/F1.patch"
    )
    (repo / rel).parent.mkdir(parents=True)
    (repo / rel).write_text("published once\n", encoding="utf-8")
    (repo / ANALYSIS / "weekly-2026-10-09.md").write_text("# kept\n", encoding="utf-8")
    _git_in(repo, env, "add", "-A")
    _git_in(repo, env, "commit", "-qm", "seed")
    if cause == "takedown":
        (store / "takedown-suppressions.txt").write_text(f"file:{rel}\n", encoding="utf-8")
    (repo / rel).unlink()  # what the stopped run's retraction left behind
    proc = _sync(env)
    assert proc.returncode == 0, proc.stderr
    tracked = set(_git_in(repo, env, "ls-files").splitlines())
    assert rel not in tracked
    assert "reports/analysis/weekly-2026-10-09.md" in tracked
