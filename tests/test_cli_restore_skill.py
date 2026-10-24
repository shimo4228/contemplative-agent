"""``restore-skill`` (ADR-0122): the human's right of return for the skill exit."""

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from contemplative_agent.cli.restore_skill import _handle_restore_skill


def _run(tmp_path: Path, **overrides) -> None:
    kwargs = {"name": "alpha", "reason": "needed again", "dry_run": False}
    kwargs.update(overrides)
    with (
        patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
        patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", tmp_path / "logs" / "audit.jsonl"),
    ):
        _handle_restore_skill(argparse.Namespace(**kwargs), MagicMock())


def _rows(tmp_path: Path) -> list[dict]:
    path = tmp_path / "logs" / "audit.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


@pytest.fixture
def archived(tmp_path: Path) -> Path:
    arch = tmp_path / "skills" / ".archive"
    arch.mkdir(parents=True)
    (arch / "alpha.md").write_text("# alpha\nbody\n", encoding="utf-8")
    return tmp_path


@pytest.mark.unit
def test_round_trip_moves_back_and_writes_one_approved_row(archived: Path) -> None:
    _run(archived)
    assert (archived / "skills" / "alpha.md").read_text() == "# alpha\nbody\n"
    assert not (archived / "skills" / ".archive" / "alpha.md").exists()
    rows = _rows(archived)
    assert [(r["command"], r["decision"], r["source"]) for r in rows] == [
        ("restore-skill", "approved", "direct-restore")
    ]
    assert rows[0]["reason"] == "needed again"


@pytest.mark.unit
def test_live_name_taken_refuses_and_overwrites_nothing(archived: Path) -> None:
    (archived / "skills" / "alpha.md").write_text("live", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        _run(archived)
    assert exc.value.code == 1
    assert (archived / "skills" / "alpha.md").read_text() == "live"
    assert (archived / "skills" / ".archive" / "alpha.md").exists()
    row = _rows(archived)[0]
    assert row["decision"] == "rejected" and "RESTORE_REFUSED_LIVE_EXISTS" in row["reason"]


@pytest.mark.unit
def test_not_archived_refuses_with_a_row(archived: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        _run(archived, name="ghost")
    assert exc.value.code == 1
    assert "RESTORE_REFUSED_NOT_ARCHIVED" in _rows(archived)[0]["reason"]


@pytest.mark.unit
def test_path_traversal_name_is_a_usage_error(archived: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        _run(archived, name="../x")
    assert exc.value.code == 2
    assert _rows(archived) == []


@pytest.mark.unit
def test_empty_reason_is_a_usage_error(archived: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        _run(archived, reason="  ")
    assert exc.value.code == 2


@pytest.mark.unit
def test_dry_run_moves_and_logs_nothing(archived: Path) -> None:
    _run(archived, dry_run=True)
    assert (archived / "skills" / ".archive" / "alpha.md").exists()
    assert _rows(archived) == []


@pytest.mark.unit
def test_symlinked_archive_dir_is_refused_and_outside_file_untouched(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "alpha.md").write_text("secret", encoding="utf-8")
    home = tmp_path / "home"
    (home / "skills").mkdir(parents=True)
    (home / "skills" / ".archive").symlink_to(outside, target_is_directory=True)
    with pytest.raises(SystemExit) as exc:
        _run(home)
    assert exc.value.code == 1
    assert (outside / "alpha.md").read_text() == "secret"
    assert not (home / "skills" / "alpha.md").exists()
    row = _rows(home)[0]
    assert row["decision"] == "rejected" and "RESTORE_REFUSED_SYMLINK" in row["reason"]
