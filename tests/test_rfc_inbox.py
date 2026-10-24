"""rfc_inbox.py (P2-03.3): numbering and publication happen at the gate."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "rfc_inbox.py"

DRAFT = "---\nid: T-X\nstate: draft\norigin: gate\nfiled_by: weekly-2026-10-23-090001\nproducer: src/a.py:3\n---\n\n## タスク\n\nthe summary line\n"


def _run(tmp: Path, *args: str, claims: Path | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(SCRIPT), "--tasks-dir", str(tmp / "rfcs"), "--project-root", str(tmp)]
    if claims:
        cmd += ["--claims-py", str(claims)]
    return subprocess.run([*cmd, *args], capture_output=True, text=True)


def _store(tmp: Path) -> Path:
    rfcs = tmp / "rfcs"
    (rfcs / ".inbox").mkdir(parents=True)
    (rfcs / "0003-old.md").write_text("---\nstate: done\n---\n\nx\n")
    (rfcs / "0009-last.md").write_text("---\nstate: draft\n---\n\nx\n")
    (rfcs / "README.md").write_text("# RFCs\n\n| # | Title |\n|---|---|\n| [0009](0009-last.md) | last |\n\nafter\n")
    return rfcs


def test_adopt_numbers_from_the_high_water_mark_and_indexes(tmp_path: Path):
    rfcs = _store(tmp_path)
    (rfcs / ".inbox" / "alpha.md").write_text(DRAFT)
    (rfcs / ".inbox" / "beta-two.md").write_text(DRAFT)
    done = _run(tmp_path, "adopt")
    assert done.returncode == 0, done.stderr
    assert (rfcs / "0010-alpha.md").read_text() == DRAFT  # frontmatter and body untouched
    assert (rfcs / "0011-beta-two.md").is_file()
    assert not list((rfcs / ".inbox").glob("*.md"))
    readme = (rfcs / "README.md").read_text()
    assert "| [0010](0010-alpha.md) | the summary line |" in readme
    assert readme.index("[0011]") > readme.index("[0010]") and readme.endswith("\nafter\n")


def test_only_adopts_the_named_drafts_and_leaves_the_rest(tmp_path: Path):
    rfcs = _store(tmp_path)
    (rfcs / ".inbox" / "keep.md").write_text(DRAFT)
    (rfcs / ".inbox" / "publish.md").write_text(DRAFT)
    assert _run(tmp_path, "adopt", "--only", "publish.md").returncode == 0
    assert (rfcs / "0010-publish.md").is_file() and (rfcs / ".inbox" / "keep.md").is_file()


def test_a_nonconforming_name_is_refused_not_moved(tmp_path: Path):
    rfcs = _store(tmp_path)
    (rfcs / ".inbox" / "Bad Name.md").write_text(DRAFT)
    done = _run(tmp_path, "adopt", "--only", "Bad Name.md")
    assert done.returncode == 1 and (rfcs / ".inbox" / "Bad Name.md").is_file()


def test_claims_recorder_is_optional_and_a_failure_is_named_not_fatal(tmp_path: Path):
    rfcs = _store(tmp_path)
    (rfcs / ".inbox" / "one.md").write_text(DRAFT)
    assert "SPAWN_RECORD" not in _run(tmp_path, "adopt").stdout  # no recorder: silent
    (rfcs / ".inbox" / "two.md").write_text(DRAFT)
    calls = tmp_path / "calls.txt"
    ok = tmp_path / "claims-ok.py"
    ok.write_text(f"import sys, pathlib\npathlib.Path({str(calls)!r}).open('a').write(' '.join(sys.argv[1:]) + '\\n')\n")
    done = _run(tmp_path, "adopt", claims=ok)
    assert done.returncode == 0
    line = calls.read_text()
    assert "spawn RFC-0011 --origin gate" in line and "--producer src/a.py:3" in line
    assert "weekly-2026-10-23-090001" in line
    (rfcs / ".inbox" / "three.md").write_text(DRAFT)
    bad = tmp_path / "claims-bad.py"
    bad.write_text("import sys; sys.exit(1)\n")
    done = _run(tmp_path, "adopt", claims=bad)
    assert done.returncode == 0 and "SPAWN_RECORD_FAIL" in done.stdout and (rfcs / "0012-three.md").is_file()


def test_list_and_a_missing_inbox(tmp_path: Path):
    rfcs = _store(tmp_path)
    (rfcs / ".inbox" / "a.md").write_text(DRAFT)
    assert _run(tmp_path, "list").stdout.split() == ["a.md"]
    empty = tmp_path / "other"
    (empty / "rfcs").mkdir(parents=True)
    done = _run(empty, "list")
    assert done.returncode == 0 and done.stdout == ""
