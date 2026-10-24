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
    (store / "views").mkdir()
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
    assert (repo / "reports" / "analysis" / "weekly-2026-10-09.md").is_file()


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
    (store / "reports" / "analysis" / "leaky.md").write_text(f"token {secret}\n", encoding="utf-8")
    proc = _sync(env)
    assert proc.returncode != 0
    assert "ERROR:" in proc.stderr and "reports/analysis/leaky.md" in proc.stderr
    assert secret not in proc.stderr + proc.stdout
    assert _commits(repo, env) == []
    assert _git_in(repo, env, "diff", "--cached", "--name-only") == ""  # nothing left staged


def test_the_words_api_key_and_bearer_do_not_stop_the_sync(tmp_path: Path) -> None:
    """Other agents' text contains them; the patterns are value shapes only."""
    env, store, repo = _sync_env(tmp_path)
    (store / "reports" / "analysis" / "talk.md").write_text(
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
    (store / "reports" / "analysis" / "weekly-2026-10-16.md").write_text(
        "# next week\n", encoding="utf-8"
    )
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
    (store / "reports" / "analysis" / "weekly-2026-10-16.md").write_text(
        "# next week\n", encoding="utf-8"
    )
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
    (store / "views").mkdir()
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
    (store / "reports" / "analysis" / "weekly-2026-10-16.md").write_text(
        "# next week\n", encoding="utf-8"
    )
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
    assert _commits(other, env), "the sync committed nothing to the repo named by MOLTBOOK_DATA_REPO"
    assert not _commits(default_repo, env), "the default repo was used although the variable was set"


def test_a_missing_data_repo_names_the_variable_that_would_fix_it(tmp_path: Path) -> None:
    env, _store, _default = _sync_env(tmp_path)
    env["MOLTBOOK_DATA_REPO"] = str(tmp_path / "no-such-repo")
    proc = _sync(env)
    assert proc.returncode != 0
    assert str(tmp_path / "no-such-repo") in proc.stderr
