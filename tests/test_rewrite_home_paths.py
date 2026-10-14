"""scripts/rewrite_home_paths.py — the one-off RFC-0051 rewrite of old files.

Pinned: the file set is what scripts/sync-research-data.sh would rsync (its own
excludes, applied by rsync — so ``logs/`` is never listed, let alone opened);
dry-run changes nothing and prints names and counts, never content; ``--apply``
replaces the home path with ``~`` and nothing else, keeps mode and mtime, and
leaves a JSON file it cannot rewrite safely (an escaped path) untouched and
reported; the exit code says whether anything is left.

Every case runs on a throwaway HOME and store under tmp_path.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "rewrite_home_paths.py"
MARKER = "a line of content that must not be printed"


@pytest.fixture
def store(tmp_path: Path) -> tuple[Path, Path]:
    home = tmp_path / "Users" / "someuser"
    root = home / ".config" / "moltbook"
    h = str(home)
    files = {
        "pipeline/value-layer/value-layer-2026-10-09.json": json.dumps(
            {"rules": {"path": f"{h}/.config/moltbook/rules", "files": 3}}, indent=2
        ),
        "reports/analysis/weekly-2026-10-09-findings.md": (
            f"{MARKER}\nCandidate file: `{h}/.config/moltbook/reports/analysis/c.txt`\n"
            f"again {h}/x\n"
        ),
        "snapshots/distill_20261001T000000Z/manifest.json": json.dumps(
            {"views_dir": f"{h}/.config/moltbook/views", "embedding_model": "nomic"}
        ),
        "pipeline/rows.jsonl": json.dumps({"p": f"{h}/a"}) + "\n" + json.dumps({"p": "b"}) + "\n",
        "reports/analysis/clean.md": "no path here\n",
        # Excluded by the sync: must be neither listed nor touched.
        "logs/audit.jsonl": json.dumps({"path": f"{h}/.config/moltbook/x"}) + "\n",
        "knowledge.json": json.dumps([{"pattern": f"{h}/p"}]),
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return home, root


def _run(home: Path, root: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--home", str(root), *extra],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "HOME": str(home)},
    )


def _snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in root.rglob("*")
        if p.is_file()
    }


def test_dry_run_lists_names_and_counts_and_changes_nothing(store) -> None:
    home, root = store
    before = _snapshot(root)
    proc = _run(home, root)
    assert proc.returncode == 0, proc.stderr
    assert _snapshot(root) == before
    out = proc.stdout
    assert "reports/analysis/weekly-2026-10-09-findings.md\t2" in out
    assert "pipeline/value-layer/value-layer-2026-10-09.json\t1" in out
    assert "snapshots/distill_20261001T000000Z/manifest.json\t1" in out
    assert "pipeline/rows.jsonl\t1" in out
    assert "clean.md" not in out
    # The sync excludes these, so the rewrite never sees them.
    assert "logs/" not in out and "knowledge.json\t" not in out
    assert MARKER not in out + proc.stderr
    assert str(home) not in out
    assert "pipeline\t2 file(s)" in out
    assert "reports\t1 file(s)" in out
    assert "snapshots\t1 file(s)" in out


def test_apply_replaces_the_home_path_and_nothing_else(store) -> None:
    home, root = store
    findings = root / "reports/analysis/weekly-2026-10-09-findings.md"
    os.chmod(findings, 0o640)
    os.utime(findings, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
    excluded = _snapshot(root)["logs/audit.jsonl"]

    proc = _run(home, root, "--apply")
    assert proc.returncode == 0, proc.stdout + proc.stderr

    text = findings.read_text(encoding="utf-8")
    assert text == (
        f"{MARKER}\nCandidate file: `~/.config/moltbook/reports/analysis/c.txt`\nagain ~/x\n"
    )
    assert findings.stat().st_mode & 0o777 == 0o640
    assert findings.stat().st_mtime_ns == 1_700_000_000_000_000_000
    layer = json.loads((root / "pipeline/value-layer/value-layer-2026-10-09.json").read_text())
    assert layer == {"rules": {"path": "~/.config/moltbook/rules", "files": 3}}
    manifest = json.loads((root / "snapshots/distill_20261001T000000Z/manifest.json").read_text())
    assert manifest == {"views_dir": "~/.config/moltbook/views", "embedding_model": "nomic"}
    # Outside the sync's set: untouched, bytes and mtime.
    assert _snapshot(root)["logs/audit.jsonl"] == excluded
    assert str(home) in (root / "knowledge.json").read_text()
    assert not list(root.rglob("*.tmp"))

    again = _run(home, root)
    assert again.returncode == 0
    assert "0 file(s)" in again.stdout


def test_a_json_file_it_cannot_rewrite_safely_is_reported_and_left_alone(store) -> None:
    home, root = store
    # The path written with escaped slashes: a text replace misses it, so the
    # rewritten JSON would still hold the home path in its value.
    tricky = root / "pipeline/escaped.json"
    tricky.write_text('{"p": "' + str(home).replace("/", "\\/") + '", "q": "' + str(home) + '"}')
    before = tricky.read_bytes()
    proc = _run(home, root, "--apply")
    assert proc.returncode == 1
    assert "pipeline/escaped.json" in proc.stdout
    assert tricky.read_bytes() == before


def test_a_symlink_is_never_followed(store, tmp_path) -> None:
    home, root = store
    outside = tmp_path / "outside.md"
    outside.write_text(f"{home}/secret\n", encoding="utf-8")
    (root / "reports/link.md").symlink_to(outside)
    proc = _run(home, root, "--apply")
    assert outside.read_text(encoding="utf-8") == f"{home}/secret\n"
    assert (root / "reports/link.md").is_symlink()
    assert proc.returncode == 0, proc.stdout


def test_a_home_path_in_another_letter_case_is_counted_and_replaced(store) -> None:
    home, root = store
    tsv = root / "reports/analysis/.anomaly-sweep-state.tsv"
    tsv.write_text(f"3\terror opening {str(home).lower()}/x\n", encoding="utf-8")
    dry = _run(home, root)
    assert "reports/analysis/.anomaly-sweep-state.tsv\t1" in dry.stdout
    assert _run(home, root, "--apply").returncode == 0
    assert tsv.read_text(encoding="utf-8") == "3\terror opening ~/x\n"


def test_an_exclude_list_without_logs_is_refused(store, tmp_path, monkeypatch, capsys) -> None:
    """The file set is scraped from the sync script; if that scrape ever loses
    `logs/` (a re-quoted pattern), the episode logs would be listed. Refuse."""
    import importlib.util

    home, root = store
    monkeypatch.setenv("HOME", str(home))
    spec = importlib.util.spec_from_file_location("rewrite_home_paths", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fake = tmp_path / "sync.sh"
    fake.write_text("rsync -a --exclude='.git/' --exclude=\"logs/\" src/ dst/\n")
    monkeypatch.setattr(module, "SYNC_SCRIPT", fake)
    before = _snapshot(root)
    assert module.scan(root, apply=True) == 2
    assert "logs/" in capsys.readouterr().err
    assert _snapshot(root) == before
