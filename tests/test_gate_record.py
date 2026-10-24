"""The approval gate's record as an act of responsibility (P1-12).

``audit.jsonl`` used to say *that* a decision happened. These tests pin what it
now says about *who*, *why* and *through which door*, and that a decision whose
record cannot be made is not carried out:

* P1-12.1 - every ``stage-*`` row carries ``reason`` / ``reason_code`` /
  ``channel`` / ``session`` / ``approver``; names FILEs take three columns and
  a signature line; ``--yes`` needs ``--reason``; a rejection needs a code.
* P1-12.2 - a rejected body is kept under ``.rejected/<ts>-<content_hash>.md``.
* P1-12.3 - an unwritable audit log means zero adoptions and exit != 0.
* P1-12.4 - ``path`` is MOLTBOOK_HOME-relative; rows validate against
  ``schemas/audit.schema.json``.
* P1-12.9 - the producer's snapshot reaches the adopt / reject row.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from contemplative_agent.cli import approval
from contemplative_agent.cli.adopt import _handle_adopt_staged
from contemplative_agent.cli.staging import StageItem, _stage_results

from ._audit_schema import validate_row


def _patches(tmp_path: Path, staged: Path):
    return (
        patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged),
        patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
        patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", tmp_path / "logs" / "audit.jsonl"),
    )


def _stage(tmp_path: Path, items, *, command="insight", snapshot=None) -> Path:
    staged = tmp_path / ".staged"
    p1, p2, p3 = _patches(tmp_path, staged)
    with p1, p2, p3:
        _stage_results(list(items), command=command, snapshot_path=snapshot)
    return staged


def _args(**overrides) -> argparse.Namespace:
    kwargs: dict = {
        "yes": False,
        "adopt_names": None,
        "archive_names": None,
        "reject_names": None,
        "reject_rest": False,
        "reason": None,
        "reason_code": None,
        "approver": None,
        "session": None,
    }
    kwargs.update(overrides)
    return argparse.Namespace(**kwargs)


def _file(tmp_path: Path, name: str, text: str) -> str:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def _run(tmp_path: Path, staged: Path, args, *, inputs=()):
    p1, p2, p3 = _patches(tmp_path, staged)
    with p1, p2, p3, patch("builtins.input", side_effect=list(inputs)):
        _handle_adopt_staged(args, MagicMock())


def _rows(tmp_path: Path) -> list[dict]:
    log = tmp_path / "logs" / "audit.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


class TestRowShape:
    def test_every_row_carries_the_gate_record_keys(self, tmp_path):
        skills = tmp_path / "skills"
        staged = _stage(
            tmp_path,
            [StageItem("a.md", "# A", skills / "a.md"), StageItem("b.md", "# B", skills / "b.md")],
            snapshot=tmp_path / "snapshots" / "insight_20261024T000000Z",
        )
        _run(
            tmp_path,
            staged,
            _args(
                adopt_names=_file(
                    tmp_path, "adopt.txt", "# approver: Test Human\na.md\t\tgood angle\n"
                ),
                reject_rest=True,
                reason_code="duplicate",
                reason="covered already",
            ),
        )
        rows = _rows(tmp_path)
        assert [r["decision"] for r in rows] == ["staged", "staged", "approved", "rejected"]
        for row in rows:
            for key in ("reason", "reason_code", "channel", "session", "approver"):
                assert key in row, (key, row)
            assert validate_row(row) == [], row

    def test_adopted_and_rejected_rows_say_who_why_and_through_which_door(self, tmp_path):
        skills = tmp_path / "skills"
        staged = _stage(
            tmp_path,
            [StageItem("a.md", "# A", skills / "a.md"), StageItem("b.md", "# B", skills / "b.md")],
        )
        _run(
            tmp_path,
            staged,
            _args(
                adopt_names=_file(
                    tmp_path, "adopt.txt", "# approver: Test Human\na.md\t\tgood angle\n"
                ),
                reject_rest=True,
                reason_code="stale",
                reason="old news",
            ),
        )
        by_decision = {r["decision"]: r for r in _rows(tmp_path)}
        adopted = by_decision["approved"]
        rejected = by_decision["rejected"]
        assert adopted["source"] == "stage-adopted-names"
        assert rejected["source"] == "stage-adopted-names", "swept by --reject-rest"
        assert adopted["reason"] == "good angle"
        assert adopted["reason_code"] is None
        assert adopted["channel"] == "names-file"
        assert adopted["approver"] == "Test Human"
        assert rejected["decision"] == "rejected"
        assert rejected["reason_code"] == "stale"
        assert rejected["reason"] == "old news"
        assert rejected["channel"] == "names-file"
        assert rejected["approver"] == "Test Human"

    def test_stage_rows_are_headless_and_carry_the_snapshot(self, tmp_path):
        skills = tmp_path / "skills"
        snap = tmp_path / "snapshots" / "insight_20261024T000000Z"
        staged = _stage(tmp_path, [StageItem("a.md", "# A", skills / "a.md")], snapshot=snap)
        (row,) = _rows(tmp_path)
        assert row["source"] == "stage"
        assert row["channel"] == "headless"
        assert row["snapshot_path"] == "snapshots/insight_20261024T000000Z"
        meta = json.loads((staged / "a.md.meta.json").read_text())
        assert meta["snapshot"] == "snapshots/insight_20261024T000000Z"

    def test_the_snapshot_rides_the_sidecar_to_the_decision_row(self, tmp_path):
        skills = tmp_path / "skills"
        staged = _stage(
            tmp_path,
            [StageItem("a.md", "# A", skills / "a.md"), StageItem("b.md", "# B", skills / "b.md")],
            snapshot=tmp_path / "snapshots" / "insight_20261024T000000Z",
        )
        _run(
            tmp_path,
            staged,
            _args(
                adopt_names=_file(tmp_path, "adopt.txt", "a.md\n"),
                reject_rest=True,
                reason_code="other",
            ),
        )
        decided = [r for r in _rows(tmp_path) if r["decision"] != "staged"]
        assert len(decided) == 2
        assert {r["snapshot_path"] for r in decided} == {"snapshots/insight_20261024T000000Z"}

    def test_a_stage_without_a_snapshot_writes_no_snapshot_key(self, tmp_path):
        skills = tmp_path / "skills"
        staged = _stage(tmp_path, [StageItem("a.md", "# A", skills / "a.md")])
        assert "snapshot" not in json.loads((staged / "a.md.meta.json").read_text())

    def test_path_is_home_relative_when_inside_the_home(self, tmp_path):
        p1, p2, p3 = _patches(tmp_path, tmp_path / ".staged")
        with p1, p2, p3:
            approval._log_approval("insight", tmp_path / "skills" / "x.md", True, "x")
            approval._log_approval("insight", Path("/elsewhere/y.md"), True, "y")
        inside, outside = _rows(tmp_path)
        assert inside["path"] == "skills/x.md"
        assert outside["path"] == "/elsewhere/y.md"

    def test_session_comes_from_the_environment_when_unflagged(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-123")
        monkeypatch.setenv("MOLTBOOK_OPERATOR", "Env Human")
        p1, p2, p3 = _patches(tmp_path, tmp_path / ".staged")
        with p1, p2, p3:
            approval._log_approval("insight", Path("a.md"), True, "a")
            approval._log_approval("insight", Path("b.md"), None, "b", source="stage")
        approved, staged = _rows(tmp_path)
        assert approved["session"] == "sess-123"
        assert approved["approver"] == "Env Human"
        assert staged["approver"] is None, "a staged row has no approver"

    def test_a_bad_reason_code_is_a_programming_error(self, tmp_path):
        p1, p2, p3 = _patches(tmp_path, tmp_path / ".staged")
        with p1, p2, p3, pytest.raises(ValueError):
            approval._log_approval("insight", Path("a.md"), False, "a", reason_code="because")


class TestRequestRules:
    def _staged(self, tmp_path):
        return _stage(tmp_path, [StageItem("a.md", "# A", tmp_path / "skills" / "a.md")])

    def test_yes_without_a_reason_aborts_and_touches_nothing(self, tmp_path, capsys):
        staged = self._staged(tmp_path)
        with pytest.raises(SystemExit) as exc:
            _run(tmp_path, staged, _args(yes=True))
        assert exc.value.code == 2
        assert "--yes requires --reason" in capsys.readouterr().err
        assert (staged / "a.md").exists()
        assert not (tmp_path / "skills" / "a.md").exists()

    def test_yes_with_a_reason_records_it(self, tmp_path):
        staged = self._staged(tmp_path)
        _run(tmp_path, staged, _args(yes=True, reason="read all of it", approver="Test Human"))
        row = _rows(tmp_path)[-1]
        assert row["source"] == "stage-adopted-auto"
        assert row["channel"] == "yes-flag"
        assert row["reason"] == "read all of it"
        assert row["approver"] == "Test Human"

    def test_a_named_rejection_without_a_code_aborts(self, tmp_path, capsys):
        staged = self._staged(tmp_path)
        with pytest.raises(SystemExit) as exc:
            _run(tmp_path, staged, _args(reject_names=_file(tmp_path, "r.txt", "a.md\n")))
        assert exc.value.code == 2
        assert "reason code" in capsys.readouterr().err
        assert (staged / "a.md").exists()

    def test_the_run_wide_code_covers_bare_names(self, tmp_path):
        staged = self._staged(tmp_path)
        _run(
            tmp_path,
            staged,
            _args(reject_names=_file(tmp_path, "r.txt", "a.md\n"), reason_code="off-constitution"),
        )
        assert _rows(tmp_path)[-1]["reason_code"] == "off-constitution"

    def test_a_lines_own_code_and_text_win(self, tmp_path):
        staged = self._staged(tmp_path)
        _run(
            tmp_path,
            staged,
            _args(
                reject_names=_file(tmp_path, "r.txt", "a.md\tlow-quality\tvague claim\n"),
                reason_code="other",
                reason="batch note",
            ),
        )
        row = _rows(tmp_path)[-1]
        assert (row["reason_code"], row["reason"]) == ("low-quality", "vague claim")

    def test_reject_rest_needs_a_code(self, tmp_path, capsys):
        staged = self._staged(tmp_path)
        with pytest.raises(SystemExit) as exc:
            _run(
                tmp_path,
                staged,
                _args(adopt_names=_file(tmp_path, "x.txt", "ghost.md\n"), reject_rest=True),
            )
        assert exc.value.code == 2
        assert "--reject-rest requires --reason-code" in capsys.readouterr().err

    def test_an_unknown_code_in_a_names_line_aborts(self, tmp_path):
        staged = self._staged(tmp_path)
        with pytest.raises(SystemExit) as exc:
            _run(tmp_path, staged, _args(reject_names=_file(tmp_path, "r.txt", "a.md\tbecause\n")))
        assert exc.value.code == 2
        assert (staged / "a.md").exists()

    def test_two_different_signers_abort(self, tmp_path):
        staged = self._staged(tmp_path)
        with pytest.raises(SystemExit) as exc:
            _run(
                tmp_path,
                staged,
                _args(
                    adopt_names=_file(tmp_path, "a.txt", "# approver: Alice\na.md\n"),
                    approver="Bob",
                ),
            )
        assert exc.value.code == 2

    def test_a_file_of_only_comments_is_an_empty_selection(self, tmp_path):
        staged = self._staged(tmp_path)
        with pytest.raises(SystemExit) as exc:
            _run(tmp_path, staged, _args(adopt_names=_file(tmp_path, "a.txt", "# approver: A\n")))
        assert exc.value.code == 2

    def test_a_bare_names_file_still_adopts(self, tmp_path):
        staged = self._staged(tmp_path)
        _run(tmp_path, staged, _args(adopt_names=_file(tmp_path, "a.txt", "a.md\n")))
        row = _rows(tmp_path)[-1]
        assert row["decision"] == "approved"
        assert row["reason"] is None and row["approver"] is None


class TestInteractiveDecline:
    def test_a_decline_at_a_terminal_asks_why(self, tmp_path):
        staged = _stage(tmp_path, [StageItem("a.md", "# A", tmp_path / "skills" / "a.md")])
        with patch("contemplative_agent.cli.approval._stdin_is_tty", return_value=True):
            _run(tmp_path, staged, _args(), inputs=["n", "stale", "superseded last week"])
        row = _rows(tmp_path)[-1]
        assert row["decision"] == "rejected"
        assert row["source"] == "stage-adopted"
        assert row["channel"] == "tty"
        assert (row["reason_code"], row["reason"]) == ("stale", "superseded last week")

    def test_enter_at_the_code_prompt_is_recorded_as_other(self, tmp_path):
        staged = _stage(tmp_path, [StageItem("a.md", "# A", tmp_path / "skills" / "a.md")])
        with patch("contemplative_agent.cli.approval._stdin_is_tty", return_value=True):
            _run(tmp_path, staged, _args(), inputs=["n", "", ""])
        assert _rows(tmp_path)[-1]["reason_code"] == "other"

    def test_a_piped_decline_is_headless_and_asks_nothing(self, tmp_path):
        staged = _stage(tmp_path, [StageItem("a.md", "# A", tmp_path / "skills" / "a.md")])
        _run(tmp_path, staged, _args(), inputs=["n"])
        row = _rows(tmp_path)[-1]
        assert row["channel"] == "headless"
        assert row["reason_code"] is None


class TestRejectedBodiesAreKept:
    def test_a_named_rejection_is_findable_by_content_hash(self, tmp_path):
        staged = _stage(tmp_path, [StageItem("a.md", "# A\nbody\n", tmp_path / "skills" / "a.md")])
        _run(tmp_path, staged, _args(reject_names=_file(tmp_path, "r.txt", "a.md\tduplicate\n")))
        row = _rows(tmp_path)[-1]
        kept = list((tmp_path / ".rejected").glob(f"*-{row['content_hash']}.md"))
        assert len(kept) == 1
        assert re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{16}\.md", kept[0].name)
        assert kept[0].read_text() == "# A\nbody\n"
        assert oct(kept[0].stat().st_mode & 0o777) == "0o600"
        assert not (staged / "a.md").exists()

    def test_a_rejected_constitution_candidate_is_kept_too(self, tmp_path):
        target = tmp_path / "constitution" / "axioms.md"
        staged = _stage(
            tmp_path, [StageItem("axioms.md", "# Amended\n", target)], command="amend-constitution"
        )
        _run(tmp_path, staged, _args(reject_names=_file(tmp_path, "r.txt", "axioms.md\tother\n")))
        row = _rows(tmp_path)[-1]
        assert row["command"] == "amend-constitution"
        assert list((tmp_path / ".rejected").glob(f"*-{row['content_hash']}.md"))

    def test_an_interactive_decline_keeps_the_canonicalized_text_the_row_hashes(self, tmp_path):
        staged = _stage(tmp_path, [StageItem("a.md", "# A", tmp_path / "skills" / "a.md")])
        _run(tmp_path, staged, _args(), inputs=["n"])
        row = _rows(tmp_path)[-1]
        (kept,) = list((tmp_path / ".rejected").glob("*.md"))
        assert kept.name.endswith(f"-{row['content_hash']}.md")
        assert approval.content_hash(kept.read_text()) == row["content_hash"]

    def test_an_unkeepable_body_blocks_the_rejection(self, tmp_path, capsys):
        staged = _stage(tmp_path, [StageItem("a.md", "# A", tmp_path / "skills" / "a.md")])
        with (
            patch("contemplative_agent.cli.approval.preserve_rejected", return_value=None),
            pytest.raises(SystemExit) as exc,
        ):
            _run(tmp_path, staged, _args(reject_names=_file(tmp_path, "r.txt", "a.md\tother\n")))
        assert exc.value.code == 1
        assert (staged / "a.md").exists(), "still staged"
        assert [r["decision"] for r in _rows(tmp_path)] == ["staged"]


class TestAFailedRecordStopsTheDecision:
    """P1-12.3: audit-first, and a failed row means the item stays staged."""

    def _fail_audit(self):
        return patch(
            "contemplative_agent.cli.approval.append_jsonl_restricted",
            side_effect=OSError("read-only fs"),
        )

    def test_an_adoption_whose_row_fails_writes_nothing(self, tmp_path, capsys):
        target = tmp_path / "skills" / "a.md"
        staged = _stage(tmp_path, [StageItem("a.md", "# A", target)])
        with self._fail_audit(), pytest.raises(SystemExit) as exc:
            _run(tmp_path, staged, _args(adopt_names=_file(tmp_path, "a.txt", "a.md\n")))
        assert exc.value.code == 1
        assert not target.exists(), "no adoption without a record"
        assert (staged / "a.md").exists() and (staged / "a.md.meta.json").exists()
        assert "left staged" in capsys.readouterr().err

    def test_a_yes_batch_adopts_zero_when_the_log_is_unwritable(self, tmp_path):
        skills = tmp_path / "skills"
        staged = _stage(
            tmp_path,
            [StageItem("a.md", "# A", skills / "a.md"), StageItem("b.md", "# B", skills / "b.md")],
        )
        with self._fail_audit(), pytest.raises(SystemExit) as exc:
            _run(tmp_path, staged, _args(yes=True, reason="read it"))
        assert exc.value.code == 1
        assert not list(skills.glob("*.md")) if skills.exists() else True

    def test_a_rejection_whose_row_fails_puts_the_item_back(self, tmp_path):
        staged = _stage(tmp_path, [StageItem("a.md", "# A", tmp_path / "skills" / "a.md")])
        with self._fail_audit(), pytest.raises(SystemExit) as exc:
            _run(tmp_path, staged, _args(reject_names=_file(tmp_path, "r.txt", "a.md\tother\n")))
        assert exc.value.code == 1
        assert (staged / "a.md").read_text() == "# A\n"
        assert json.loads((staged / "a.md.meta.json").read_text())["command"] == "insight"
        kept = tmp_path / ".rejected"
        assert not kept.exists() or not list(kept.glob("*.md")), "no orphan copy"

    def test_a_declined_prompt_whose_row_fails_leaves_the_item_staged(self, tmp_path):
        staged = _stage(tmp_path, [StageItem("a.md", "# A", tmp_path / "skills" / "a.md")])
        with self._fail_audit(), pytest.raises(SystemExit) as exc:
            _run(tmp_path, staged, _args(), inputs=["n"])
        assert exc.value.code == 1
        assert (staged / "a.md").exists()
