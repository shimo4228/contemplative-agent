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
