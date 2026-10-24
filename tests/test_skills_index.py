"""Tests for scripts/skills_index.py (P2-05.8): row count, columns, privacy."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import skills_index as si  # noqa: E402  # pyright: ignore[reportMissingImports]


def _skill(d: Path, stem: str, name: str, extra: str = "") -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{stem}.md").write_text(
        f'---\nname: {name}\ndescription: "secret body words"\norigin: auto-extracted\n{extra}---\n\n# T\nbody\n'
    )


def _audit(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _fixture(tmp: Path) -> tuple[Path, Path, Path]:
    skills, archive, audit = tmp / "skills", tmp / "archive", tmp / "audit.jsonl"
    _skill(skills, "alpha-20260701", "alpha")
    _skill(skills, "beta", "beta-renamed")
    _skill(archive, "old-one", "old-one", "superseded_by: alpha\n")
    _audit(
        audit,
        [
            {
                "ts": "2026-07-01T00:00:00Z",
                "path": "/Users/x/skills/alpha-20260701.md",
                "decision": "approved",
                "source": "stage-adopted-names",
                "reason": "PRIVATE REASON",
            },
            {
                "ts": "2026-07-09T00:00:00Z",
                "path": "skills/alpha-20260701.md",
                "decision": "approved",
                "source": "direct",
            },
            {
                "ts": "2026-08-01T00:00:00Z",
                "path": "skills/old-one.md",
                "decision": "approved",
                "source": "direct-archive",
            },
            {
                "ts": "2026-08-02T00:00:00Z",
                "path": "skills/beta.md",
                "decision": "rejected",
                "source": "stage-rejected-names",
            },
        ],
    )
    return skills, archive, audit


def test_row_count_is_live_plus_retired(tmp_path: Path) -> None:
    skills, archive, audit = _fixture(tmp_path)
    live, retired = si.build(skills, archive, audit)
    assert len(live) + len(retired) == len(list(skills.glob("*.md"))) + len(
        list(archive.glob("*.md"))
    )
    assert [r["stem"] for r in live] == ["alpha-20260701", "beta"]
    assert [r["name"] for r in live] == ["alpha", "beta-renamed"]  # name != stem is kept visible


def test_adoption_columns_from_audit(tmp_path: Path) -> None:
    skills, archive, audit = _fixture(tmp_path)
    live, retired = si.build(skills, archive, audit)
    alpha, beta = live
    assert alpha["adopted_at"] == "2026-07-01T00:00:00Z"  # earliest adopting row
    assert alpha["source"] == "stage-adopted-names"
    assert beta["adopted_at"] is None and beta["adopted_at_reason"] == "no_audit_row"
    assert retired == [
        {
            "stem": "old-one",
            "name": "old-one",
            "status": "archived",
            "retired_at": "2026-08-01T00:00:00Z",
            "superseded_by": "alpha",
        }
    ]


def test_outputs_carry_no_body_or_reason(tmp_path: Path) -> None:
    skills, archive, audit = _fixture(tmp_path)
    res = subprocess.run(
        [
            sys.executable,
            "-I",
            str(SCRIPTS / "skills_index.py"),
            "--skills",
            str(skills),
            "--archive",
            str(archive),
            "--audit",
            str(audit),
            "--out-md",
            str(skills / "INDEX.md"),
            "--out-json",
            str(tmp_path / "p" / "idx.json"),
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stderr
    assert "live=2 retired=1 rows=3 skills/*.md=2" in res.stdout
    blob = (skills / "INDEX.md").read_text() + (tmp_path / "p" / "idx.json").read_text()
    assert "secret body words" not in blob and "PRIVATE REASON" not in blob
    assert "/Users/" not in blob
    # a second run does not count its own INDEX.md as a skill
    again = subprocess.run(
        [
            sys.executable,
            "-I",
            str(SCRIPTS / "skills_index.py"),
            "--skills",
            str(skills),
            "--out-md",
            str(skills / "INDEX.md"),
            "--out-json",
            str(tmp_path / "p" / "idx.json"),
        ],
        capture_output=True,
        text=True,
    )
    assert again.returncode == 0 and "skills/*.md=2" in again.stdout


def test_no_archive_no_audit_still_works(tmp_path: Path) -> None:
    skills = tmp_path / "skills"
    _skill(skills, "a", "a")
    live, retired = si.build(skills, None, None)
    assert len(live) == 1 and retired == []
