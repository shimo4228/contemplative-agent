"""The skill store's archive exit (ADR-0097 Decision 5).

Retiring a skill moves it to ``skills/.archive/`` instead of unlinking it, so
the store can shrink without the content becoming unrecoverable. Two entry
points, one primitive:

* ``remove-skill`` archives by default; ``--delete`` is the explicit
  irreversible flag. ``--reason`` stays mandatory on both (the CREW library
  weeding finding in ADR-0097's Context: 98% of weeding candidates were
  retained until a written reason was required).
* ``adopt-staged --archive-names FILE`` archives store skills named in an
  operator-typed file, mirroring ``--adopt-names`` / ``--hold-names``.

The tests that matter most are the three destructive-path contracts: an
unknown name aborts before anything moves, an archived skill really leaves
the store, and an adopt with no ``--archive-names`` behaves exactly as it did
before this landed.
"""

import argparse
import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from contemplative_agent.cli.adopt import _handle_adopt_staged, _handle_remove_skill
from contemplative_agent.cli.staging import StageItem, _stage_results
from contemplative_agent.core.skill_selection import load_skill_catalog


def _stage(tmp_path: Path, items, command: str = "insight") -> Path:
    staged_dir = tmp_path / ".staged"
    with (
        patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
        patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
        patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", tmp_path / "logs" / "audit.jsonl"),
    ):
        _stage_results(list(items), command=command)
    return staged_dir


def _names_file(tmp_path: Path, filename: str, lines) -> str:
    path = tmp_path / filename
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return str(path)


def _adopt_args(**overrides) -> argparse.Namespace:
    kwargs: dict = {
        "yes": False,
        "adopt_names": None,
        "hold_names": None,
        "archive_names": None,
        "reject_rest": False,
    }
    kwargs.update(overrides)
    return argparse.Namespace(**kwargs)


def _run_adopt(tmp_path: Path, staged_dir: Path, args, *, inputs=None):
    with (
        patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
        patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
        patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", tmp_path / "logs" / "audit.jsonl"),
        patch("builtins.input", side_effect=inputs or []),
    ):
        _handle_adopt_staged(args, MagicMock())


def _audit(tmp_path: Path) -> list[dict]:
    log = tmp_path / "logs" / "audit.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().strip().splitlines()]


def _make_skill(tmp_path: Path, name: str, body: str) -> Path:
    skills = tmp_path / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    path = skills / name
    path.write_text(body, encoding="utf-8")
    return path


class TestArchiveNamesSafetyContracts:
    """`--archive-names` mirrors the abort contracts of `--adopt-names`."""

    def test_unknown_name_aborts_before_any_move(self, tmp_path):
        """One name that no store skill matches must leave everything alone."""
        old = _make_skill(tmp_path, "old.md", "---\nname: old\n---\n\n# Old\n")
        staged = _stage(tmp_path, [StageItem("new.md", "# New", tmp_path / "skills" / "new.md")])
        args = _adopt_args(
            adopt_names=_names_file(tmp_path, "adopt.txt", ["new.md"]),
            archive_names=_names_file(tmp_path, "archive.txt", ["old.md", "typo.md"]),
        )
        with pytest.raises(SystemExit) as exc:
            _run_adopt(tmp_path, staged, args)
        assert exc.value.code == 2
        assert old.read_text() == "---\nname: old\n---\n\n# Old\n"
        assert not (tmp_path / "skills" / ".archive").exists()
        assert (staged / "new.md").exists(), "staging must be untouched"
        assert not (tmp_path / "skills" / "new.md").exists()

    def test_empty_archive_names_file_aborts(self, tmp_path):
        _make_skill(tmp_path, "old.md", "# Old\n")
        staged = _stage(tmp_path, [StageItem("new.md", "# New", tmp_path / "skills" / "new.md")])
        empty = tmp_path / "archive.txt"
        empty.write_text("\n  \n", encoding="utf-8")
        args = _adopt_args(archive_names=str(empty))
        with pytest.raises(SystemExit) as exc:
            _run_adopt(tmp_path, staged, args)
        assert exc.value.code == 2
        assert (tmp_path / "skills" / "old.md").exists()

    def test_a_name_in_two_of_the_three_files_aborts(self, tmp_path):
        _make_skill(tmp_path, "both.md", "# Both\n")
        staged = _stage(tmp_path, [StageItem("both.md", "# New", tmp_path / "skills" / "both.md")])
        args = _adopt_args(
            adopt_names=_names_file(tmp_path, "adopt.txt", ["both.md"]),
            archive_names=_names_file(tmp_path, "archive.txt", ["both.md"]),
        )
        with pytest.raises(SystemExit) as exc:
            _run_adopt(tmp_path, staged, args)
        assert exc.value.code == 2
        assert (staged / "both.md").exists()
        assert not (tmp_path / "skills" / ".archive").exists()

    def test_a_name_in_hold_and_archive_aborts_too(self, tmp_path):
        """All three pairs are checked, not just the historical adopt/hold one."""
        _make_skill(tmp_path, "both.md", "# Both\n")
        staged = _stage(tmp_path, [StageItem("both.md", "# New", tmp_path / "skills" / "both.md")])
        args = _adopt_args(
            hold_names=_names_file(tmp_path, "hold.txt", ["both.md"]),
            archive_names=_names_file(tmp_path, "archive.txt", ["both.md"]),
        )
        with pytest.raises(SystemExit) as exc:
            _run_adopt(tmp_path, staged, args)
        assert exc.value.code == 2
        assert (tmp_path / "skills" / "both.md").exists()

    def test_a_malformed_line_aborts_rather_than_dropping_the_pairing(self, tmp_path):
        """A dropped pairing would archive the skill and lose its successor."""
        _make_skill(tmp_path, "old.md", "# Old\n")
        staged = _stage(tmp_path, [StageItem("new.md", "# New", tmp_path / "skills" / "new.md")])
        args = _adopt_args(
            adopt_names=_names_file(tmp_path, "adopt.txt", ["new.md"]),
            archive_names=_names_file(tmp_path, "archive.txt", ["old.md -> new.md"]),
        )
        with pytest.raises(SystemExit) as exc:
            _run_adopt(tmp_path, staged, args)
        assert exc.value.code == 2
        assert (tmp_path / "skills" / "old.md").exists()

    def test_the_same_skill_with_two_successors_aborts(self, tmp_path):
        _make_skill(tmp_path, "old.md", "# Old\n")
        skills = tmp_path / "skills"
        staged = _stage(
            tmp_path,
            [
                StageItem("a.md", "# A", skills / "a.md"),
                StageItem("b.md", "# B", skills / "b.md"),
            ],
        )
        args = _adopt_args(
            adopt_names=_names_file(tmp_path, "adopt.txt", ["a.md", "b.md"]),
            archive_names=_names_file(
                tmp_path,
                "archive.txt",
                ["old.md superseded-by a.md", "old.md superseded-by b.md"],
            ),
        )
        with pytest.raises(SystemExit) as exc:
            _run_adopt(tmp_path, staged, args)
        assert exc.value.code == 2
        assert (skills / "old.md").exists()

    def test_a_successor_that_is_not_being_adopted_aborts(self, tmp_path):
        """A supersede promises the replacement lands in the same run."""
        _make_skill(tmp_path, "old.md", "# Old\n")
        skills = tmp_path / "skills"
        staged = _stage(
            tmp_path,
            [
                StageItem("new.md", "# New", skills / "new.md"),
                StageItem("other.md", "# Other", skills / "other.md"),
            ],
        )
        args = _adopt_args(
            adopt_names=_names_file(tmp_path, "adopt.txt", ["other.md"]),
            archive_names=_names_file(tmp_path, "archive.txt", ["old.md superseded-by new.md"]),
        )
        with pytest.raises(SystemExit) as exc:
            _run_adopt(tmp_path, staged, args)
        assert exc.value.code == 2
        assert (skills / "old.md").exists()
        assert (staged / "other.md").exists(), "staging must be untouched"

    def test_a_successor_that_does_not_write_into_the_store_aborts(self, tmp_path):
        """Code review 2026-08-22 CRITICAL.

        ADR-0097 D5 scopes both frontmatter halves to skills. Without this
        check a `distill-identity` item could be named as a successor, and
        the stamp synthesized a whole frontmatter block onto `identity.md` —
        a file that has none by design and is injected verbatim into every
        session's system prompt.
        """
        _make_skill(tmp_path, "old.md", "# Old\n")
        staged = _stage(
            tmp_path,
            [StageItem("identity.md", "I am a contemplative agent.\n", tmp_path / "identity.md")],
            command="distill-identity",
        )
        args = _adopt_args(
            adopt_names=_names_file(tmp_path, "adopt.txt", ["identity.md"]),
            archive_names=_names_file(
                tmp_path, "archive.txt", ["old.md superseded-by identity.md"]
            ),
        )
        with pytest.raises(SystemExit) as exc:
            _run_adopt(tmp_path, staged, args)
        assert exc.value.code == 2
        assert (tmp_path / "skills" / "old.md").exists()
        assert not (tmp_path / "identity.md").exists()
        assert (staged / "identity.md").exists(), "staging must be untouched"

    def test_a_successor_that_is_not_staged_at_all_aborts(self, tmp_path):
        _make_skill(tmp_path, "old.md", "# Old\n")
        staged = _stage(tmp_path, [StageItem("new.md", "# New", tmp_path / "skills" / "new.md")])
        args = _adopt_args(
            archive_names=_names_file(tmp_path, "archive.txt", ["old.md superseded-by ghost.md"]),
        )
        with pytest.raises(SystemExit) as exc:
            _run_adopt(tmp_path, staged, args)
        assert exc.value.code == 2
        assert (tmp_path / "skills" / "old.md").exists()
        assert (staged / "new.md").exists()


class TestArchiveAtTheAdoptGate:
    def test_an_archived_skill_leaves_the_store(self, tmp_path):
        old = _make_skill(tmp_path, "old.md", "---\nname: old\n---\n\n# Old body\n")
        staged = _stage(tmp_path, [StageItem("new.md", "# New", tmp_path / "skills" / "new.md")])
        args = _adopt_args(
            adopt_names=_names_file(tmp_path, "adopt.txt", ["new.md"]),
            archive_names=_names_file(tmp_path, "archive.txt", ["old.md"]),
        )
        _run_adopt(tmp_path, staged, args)

        assert not old.exists(), "the store must not still hold the archived skill"
        archived = tmp_path / "skills" / ".archive" / "old.md"
        assert archived.is_file(), "the content must survive the exit"
        assert "# Old body" in archived.read_text()
        assert (tmp_path / "skills" / "new.md").read_text().endswith("# New\n")

    def test_the_archive_is_invisible_to_the_store_and_a_mv_restores_it(self, tmp_path):
        """The exit rests on every reader globbing `skills/*.md` flatly.

        Also the whole restore story: no command, just a rename back. If the
        catalog were recursive the archive would keep injecting what the
        operator retired, and the exit would be theatre.
        """
        skills = tmp_path / "skills"
        _make_skill(tmp_path, "old.md", "---\nname: old\n---\n\n# Old\n")
        _make_skill(tmp_path, "stays.md", "---\nname: stays\n---\n\n# Stays\n")
        args = _adopt_args(archive_names=_names_file(tmp_path, "archive.txt", ["old.md"]))
        _run_adopt(tmp_path, tmp_path / ".staged", args)

        assert [e.name for e in load_skill_catalog(skills)] == ["stays"]

        (skills / ".archive" / "old.md").rename(skills / "old.md")
        assert sorted(e.name for e in load_skill_catalog(skills)) == ["old", "stays"]

    def test_an_archive_only_run_works_with_nothing_staged(self, tmp_path):
        """The never-selected exit runs on weeks the pipeline staged nothing."""
        skill = _make_skill(tmp_path, "never-selected.md", "# Never\n")
        args = _adopt_args(
            archive_names=_names_file(tmp_path, "archive.txt", ["never-selected.md"])
        )
        _run_adopt(tmp_path, tmp_path / ".staged", args)
        assert not skill.exists()
        assert (tmp_path / "skills" / ".archive" / "never-selected.md").is_file()

    def test_both_halves_of_a_supersede_are_recorded(self, tmp_path):
        skills = tmp_path / "skills"
        _make_skill(tmp_path, "old.md", "---\nname: old\n---\n\n# Old\n")
        staged = _stage(
            tmp_path,
            [StageItem("new.md", "---\nname: new\n---\n\n# New\n", skills / "new.md")],
        )
        args = _adopt_args(
            adopt_names=_names_file(tmp_path, "adopt.txt", ["new.md"]),
            archive_names=_names_file(tmp_path, "archive.txt", ["old.md superseded-by new.md"]),
        )
        _run_adopt(tmp_path, staged, args)

        assert "supersedes: old.md" in (skills / "new.md").read_text()
        assert "superseded_by: new.md" in (skills / ".archive" / "old.md").read_text()

    def test_one_survivor_can_supersede_several_variants(self, tmp_path):
        skills = tmp_path / "skills"
        _make_skill(tmp_path, "v1.md", "---\nname: v1\n---\n\n# V1\n")
        _make_skill(tmp_path, "v2.md", "---\nname: v2\n---\n\n# V2\n")
        staged = _stage(
            tmp_path,
            [StageItem("merged.md", "---\nname: merged\n---\n\n# Merged\n", skills / "merged.md")],
        )
        args = _adopt_args(
            adopt_names=_names_file(tmp_path, "adopt.txt", ["merged.md"]),
            archive_names=_names_file(
                tmp_path,
                "archive.txt",
                ["v2.md superseded-by merged.md", "v1.md superseded-by merged.md"],
            ),
        )
        _run_adopt(tmp_path, staged, args)
        assert "supersedes: v1.md, v2.md" in (skills / "merged.md").read_text()

    def test_a_standalone_archive_records_no_successor(self, tmp_path):
        """A `superseded_by:` with nothing after it is a pointer to nowhere."""
        _make_skill(tmp_path, "old.md", "---\nname: old\n---\n\n# Old\n")
        args = _adopt_args(archive_names=_names_file(tmp_path, "archive.txt", ["old.md"]))
        _run_adopt(tmp_path, tmp_path / ".staged", args)
        assert "superseded_by" not in (tmp_path / "skills" / ".archive" / "old.md").read_text()

    def test_the_audit_row_names_the_archive_destination(self, tmp_path):
        """The discriminator: `.archive/` in `path` means archived, not deleted."""
        _make_skill(tmp_path, "old.md", "# Old\n")
        args = _adopt_args(archive_names=_names_file(tmp_path, "archive.txt", ["old.md"]))
        _run_adopt(tmp_path, tmp_path / ".staged", args)
        row = _audit(tmp_path)[-1]
        assert row["command"] == "adopt-staged"
        assert row["decision"] == "approved"
        assert "ADR-0097 D5 archive exit" in row["reason"]
        # `source` is the discriminator, not `path` — a purge from the archive
        # also carries an `.archive/` path (silent-failure review HIGH 2).
        # Transcribed from the names file, never prompted, even here where the
        # run carried no --adopt-names and would otherwise be "stage-adopted".
        assert row["source"] == "stage-archived-names"
        assert Path(row["path"]).parent.name == ".archive", "names the file a mv restores"

    def test_a_paired_archive_names_its_successor_in_the_audit_reason(self, tmp_path):
        skills = tmp_path / "skills"
        _make_skill(tmp_path, "old.md", "# Old\n")
        staged = _stage(tmp_path, [StageItem("new.md", "# New", skills / "new.md")])
        args = _adopt_args(
            adopt_names=_names_file(tmp_path, "adopt.txt", ["new.md"]),
            archive_names=_names_file(tmp_path, "archive.txt", ["old.md superseded-by new.md"]),
        )
        _run_adopt(tmp_path, staged, args)
        row = _audit(tmp_path)[-1]
        assert row["reason"] == "superseded by new.md (ADR-0097 D5 archive exit)"

    def test_a_declined_successor_leaves_its_predecessor_in_the_store(self, tmp_path):
        """The store must not lose a skill whose replacement never landed."""
        skills = tmp_path / "skills"
        old = _make_skill(tmp_path, "old.md", "# Old\n")
        staged = _stage(tmp_path, [StageItem("new.md", "# New", skills / "new.md")])
        args = _adopt_args(
            archive_names=_names_file(tmp_path, "archive.txt", ["old.md superseded-by new.md"]),
        )
        with pytest.raises(SystemExit) as exc:
            _run_adopt(tmp_path, staged, args, inputs=["n"])
        assert exc.value.code == 1
        assert old.read_text() == "# Old\n"
        assert not (skills / ".archive").exists()
        assert not (skills / "new.md").exists()

    def test_a_failed_archive_is_not_exit_zero(self, tmp_path, capsys):
        skills = tmp_path / "skills"
        old = _make_skill(tmp_path, "old.md", "# Old\n")
        # A regular file where the archive directory belongs: the mkdir fails.
        (skills / ".archive").write_text("not a directory", encoding="utf-8")
        args = _adopt_args(archive_names=_names_file(tmp_path, "archive.txt", ["old.md"]))
        with pytest.raises(SystemExit) as exc:
            _run_adopt(tmp_path, tmp_path / ".staged", args)
        assert exc.value.code == 1
        assert old.exists(), "a failed archive must leave the skill in the store"
        captured = capsys.readouterr()
        assert "ARCHIVE_REFUSED_BAD_DESTINATION" in captured.err
        assert "0 archived" in captured.out
        assert "1 archive FAILURES" in captured.out
        # Every outcome writes a row, refusals included — a refused archive
        # that logs nothing is indistinguishable from a command nobody ran
        # (silent-failure review MEDIUM 8).
        row = _audit(tmp_path)[-1]
        assert row["decision"] == "rejected"
        assert "ARCHIVE_REFUSED_BAD_DESTINATION" in row["reason"]

    def test_a_symlinked_store_skill_is_refused_at_plan_time(self, tmp_path, capsys):
        """Code review 2026-08-22 MEDIUM 4.

        The primitive always refused it, but only after the successor had
        been adopted with `supersedes:` stamped — store holding both, exit 1.
        Symlink-ness is knowable before anything moves, so it joins the "one
        typo leaves every skill where it is" contract: exit 2, untouched.
        """
        skills = tmp_path / "skills"
        real = _make_skill(tmp_path, "real.md", "# Real\n")
        (skills / "link.md").symlink_to(real)
        staged = _stage(tmp_path, [StageItem("new.md", "# New", skills / "new.md")])
        args = _adopt_args(
            adopt_names=_names_file(tmp_path, "adopt.txt", ["new.md"]),
            archive_names=_names_file(tmp_path, "archive.txt", ["link.md superseded-by new.md"]),
        )
        with pytest.raises(SystemExit) as exc:
            _run_adopt(tmp_path, staged, args)
        assert exc.value.code == 2
        assert (skills / "link.md").is_symlink()
        assert real.exists()
        assert not (skills / "new.md").exists(), "the successor must not be adopted"
        assert (staged / "new.md").exists()
        assert "symlink" in capsys.readouterr().err

    def test_a_skill_this_run_adopted_into_is_not_archived(self, tmp_path, capsys):
        """Otherwise the approved adoption would vanish into `.archive/`.

        Reached when a staged item's TARGET is the archived skill (which the
        name-overlap check cannot see: it compares staged names against store
        names) and the text is identical, so the collision guard writes in
        place instead of minting a twin.
        """
        skills = tmp_path / "skills"
        old = _make_skill(tmp_path, "old.md", "# Same\n")
        staged = _stage(tmp_path, [StageItem("candidate.md", "# Same\n", skills / "old.md")])
        args = _adopt_args(
            adopt_names=_names_file(tmp_path, "adopt.txt", ["candidate.md"]),
            archive_names=_names_file(tmp_path, "archive.txt", ["old.md"]),
        )
        with pytest.raises(SystemExit) as exc:
            _run_adopt(tmp_path, staged, args)
        assert exc.value.code == 1
        assert old.read_text() == "# Same\n"
        assert not (skills / ".archive").exists()
        assert "ARCHIVE_REFUSED_JUST_ADOPTED" in capsys.readouterr().err

    def test_a_failed_unlink_leaves_a_duplicate_not_a_hole(self, tmp_path):
        """Copy-then-unlink, in that order: an interruption must not lose text."""
        skills = tmp_path / "skills"
        old = _make_skill(tmp_path, "old.md", "# Old\n")
        args = _adopt_args(archive_names=_names_file(tmp_path, "archive.txt", ["old.md"]))
        real_unlink = Path.unlink

        def _refuse_source(self, *a, **kw):
            if self == old:
                raise OSError("device busy")
            return real_unlink(self, *a, **kw)

        with patch.object(Path, "unlink", _refuse_source), pytest.raises(SystemExit) as exc:
            _run_adopt(tmp_path, tmp_path / ".staged", args)
        assert exc.value.code == 1
        assert old.exists(), "the source must survive a failed move"
        stray = skills / ".archive" / "old.md"
        assert stray.read_text() == "# Old\n"
        # Bytes landed in the archive, so the trail must name them — and must
        # not claim the retirement took effect (security review 2026-08-22).
        row = _audit(tmp_path)[-1]
        assert Path(row["path"]) == stray
        assert row["decision"] == "rejected"
        assert "ARCHIVE_SOURCE_LEFT_BEHIND" in row["reason"]

    def test_an_archive_dir_symlinked_back_into_the_store_destroys_nothing(self, tmp_path):
        """Security review 2026-08-22 MEDIUM, second spelling.

        With `skills/.archive -> skills/`, the destination resolves to the
        source: both ends pass containment (pointing *inside* is what defeats
        that predicate) and the H5 guard hands back the source itself because
        a file's content trivially equals its own. Write-then-unlink then
        deleted the skill and logged it as an archive, exit 0.
        """
        skills = tmp_path / "skills"
        old = _make_skill(tmp_path, "old.md", "# Old\n")
        (skills / ".archive").symlink_to(skills, target_is_directory=True)
        args = _adopt_args(archive_names=_names_file(tmp_path, "archive.txt", ["old.md"]))
        with pytest.raises(SystemExit) as exc:
            _run_adopt(tmp_path, tmp_path / ".staged", args)
        assert exc.value.code == 1
        assert old.read_text() == "# Old\n", "the only copy must survive"
        row = _audit(tmp_path)[-1]
        assert row["decision"] == "rejected"
        assert "ARCHIVE_REFUSED_NOT_A_MOVE" in row["reason"]

    def test_a_failed_paired_archive_names_the_stamp_that_needs_repair(self, tmp_path, capsys):
        """The one residual state the ordering cannot prevent, said out loud."""
        skills = tmp_path / "skills"
        old = _make_skill(tmp_path, "old.md", "# Old\n")
        (skills / ".archive").write_text("not a directory", encoding="utf-8")
        staged = _stage(
            tmp_path,
            [StageItem("new.md", "---\nname: new\n---\n\n# New\n", skills / "new.md")],
        )
        args = _adopt_args(
            adopt_names=_names_file(tmp_path, "adopt.txt", ["new.md"]),
            archive_names=_names_file(tmp_path, "archive.txt", ["old.md superseded-by new.md"]),
        )
        with pytest.raises(SystemExit) as exc:
            _run_adopt(tmp_path, staged, args)
        assert exc.value.code == 1
        assert old.exists()
        assert "supersedes: old.md" in (skills / "new.md").read_text()
        err = capsys.readouterr().err
        assert "Repair needed" in err and "new.md" in err and "old.md" in err

    def test_the_budget_reading_never_sees_a_candidate_the_loop_refuses(self, tmp_path, capsys):
        """The instrument keeps its own symlink guard as defence in depth, but
        the plan aborts first now, so a candidate the loop would refuse cannot
        reach a reading the operator approves against."""
        skills = tmp_path / "skills"
        real = _make_skill(tmp_path, "real.md", "# Real\n" + ("filler words here. " * 400))
        (skills / "link.md").symlink_to(real)
        args = _adopt_args(archive_names=_names_file(tmp_path, "archive.txt", ["link.md"]))
        with pytest.raises(SystemExit) as exc:
            _run_adopt(tmp_path, tmp_path / ".staged", args)
        assert exc.value.code == 2
        assert "tok after this batch" not in capsys.readouterr().out

    def test_a_completed_move_with_a_failed_audit_write_is_not_success(self, tmp_path, capsys):
        """Codex P2 #1. The store lost a skill and the trail said nothing."""
        skills = tmp_path / "skills"
        _make_skill(tmp_path, "old.md", "# Old\n")
        args = _adopt_args(archive_names=_names_file(tmp_path, "archive.txt", ["old.md"]))
        with (
            patch(
                "contemplative_agent.cli.approval.append_jsonl_restricted",
                side_effect=OSError("read-only fs"),
            ),
            pytest.raises(SystemExit) as exc,
        ):
            _run_adopt(tmp_path, tmp_path / ".staged", args)
        assert exc.value.code == 1
        assert (skills / ".archive" / "old.md").is_file(), "the move happened"
        captured = capsys.readouterr()
        assert "ARCHIVE_UNRECORDED" in captured.err
        assert "1 archive FAILURES" in captured.out

    def test_a_paired_archive_whose_name_is_taken_refuses_rather_than_mispoint(self, tmp_path):
        """Silent-failure review MEDIUM 7.

        `supersedes:` is fixed before the collision guard runs, so a renamed
        destination would leave the survivor pointing at `.archive/old.md` —
        an unrelated earlier retirement — while its own text sits at
        `.archive/old-2.md`.
        """
        skills = tmp_path / "skills"
        archive = skills / ".archive"
        archive.mkdir(parents=True)
        (archive / "old.md").write_text("# An unrelated earlier retirement\n", encoding="utf-8")
        old = _make_skill(tmp_path, "old.md", "# A different body\n")
        staged = _stage(tmp_path, [StageItem("new.md", "# New", skills / "new.md")])
        args = _adopt_args(
            adopt_names=_names_file(tmp_path, "adopt.txt", ["new.md"]),
            archive_names=_names_file(tmp_path, "archive.txt", ["old.md superseded-by new.md"]),
        )
        with pytest.raises(SystemExit) as exc:
            _run_adopt(tmp_path, staged, args)
        assert exc.value.code == 1
        assert old.exists(), "no mispointed lineage, and nothing moved"
        assert not (archive / "old-2.md").exists()
        assert (archive / "old.md").read_text() == "# An unrelated earlier retirement\n"
        assert "supersedes: old.md" in (skills / "new.md").read_text()

    def test_a_standalone_archive_of_a_legacy_skill_is_byte_identical(self, tmp_path):
        """No frontmatter is invented when nothing needs to be recorded."""
        body = "# Hand written\n\nnot from the extraction pipeline\n"
        _make_skill(tmp_path, "legacy.md", body)
        args = _adopt_args(archive_names=_names_file(tmp_path, "archive.txt", ["legacy.md"]))
        _run_adopt(tmp_path, tmp_path / ".staged", args)
        assert (tmp_path / "skills" / ".archive" / "legacy.md").read_text() == body

    def test_a_paired_archive_never_fabricates_provenance(self, tmp_path, capsys):
        """Silent-failure review MEDIUM 6.

        `origin: auto-extracted` is the harness's word for extraction-pipeline
        output. Stamped onto a hand-written skill it is a false claim, and
        restoring is a plain `mv`, so the claim comes back into the store.
        """
        skills = tmp_path / "skills"
        _make_skill(tmp_path, "legacy.md", "# Hand written\n\nprose\n")
        staged = _stage(tmp_path, [StageItem("new.md", "# New", skills / "new.md")])
        args = _adopt_args(
            adopt_names=_names_file(tmp_path, "adopt.txt", ["new.md"]),
            archive_names=_names_file(tmp_path, "archive.txt", ["legacy.md superseded-by new.md"]),
        )
        _run_adopt(tmp_path, staged, args)
        archived = (skills / ".archive" / "legacy.md").read_text()
        assert "superseded_by: new.md" in archived
        assert "origin:" not in archived
        assert "name:" not in archived
        assert "# Hand written" in archived
        # The one non-byte-identical archive says so rather than being found
        # by diffing later.
        assert "Adding a frontmatter block to legacy.md" in capsys.readouterr().out

    def test_an_already_archived_name_is_a_no_op_not_an_abort(self, tmp_path, capsys):
        """Silent-failure review MEDIUM 5 — re-running a packet after a
        partial archive must not misdiagnose the state as a typo, and must not
        block the adoptions sharing the invocation."""
        skills = tmp_path / "skills"
        archive = skills / ".archive"
        archive.mkdir(parents=True)
        (archive / "done.md").write_text("# Done\n", encoding="utf-8")
        old = _make_skill(tmp_path, "still-here.md", "# Still\n")
        staged = _stage(tmp_path, [StageItem("new.md", "# New", skills / "new.md")])
        args = _adopt_args(
            adopt_names=_names_file(tmp_path, "adopt.txt", ["new.md"]),
            archive_names=_names_file(tmp_path, "archive.txt", ["done.md", "still-here.md"]),
        )
        _run_adopt(tmp_path, staged, args)
        assert (skills / "new.md").exists(), "the adoptions must not be blocked"
        assert not old.exists()
        assert (archive / "still-here.md").is_file()
        assert (archive / "done.md").read_text() == "# Done\n", "untouched"
        assert "Already in the archive" in capsys.readouterr().err

    def test_a_name_that_is_neither_live_nor_archived_still_aborts(self, tmp_path, capsys):
        _make_skill(tmp_path, "real.md", "# Real\n")
        args = _adopt_args(archive_names=_names_file(tmp_path, "archive.txt", ["ghost.md"]))
        with pytest.raises(SystemExit) as exc:
            _run_adopt(tmp_path, tmp_path / ".staged", args)
        assert exc.value.code == 2
        assert "already in .archive/" in capsys.readouterr().err, "names the right repair"

    def test_a_sidecar_rewritten_after_the_plan_cannot_slip_a_non_skill_successor(self, tmp_path):
        """Silent-failure review LOW 10 — snapshot discipline.

        The plan's successor-is-a-skill gate read a FRESH sidecar; the write
        uses the snapshot `_load_staged_item` validated. A `.staged/` rewrite
        in between defeated a check made on the other one: reproduced as
        `old.md` archived with `superseded_by: identity-2.md`, exit 0. The
        rewrite is injected at the seam between plan and loop.
        """
        skills = tmp_path / "skills"
        old = _make_skill(tmp_path, "old.md", "# Old\n")
        staged = _stage(tmp_path, [StageItem("new.md", "# New", skills / "new.md")])
        meta_file = staged / "new.md.meta.json"

        def _rewrite_sidecar(*_a, **_kw):
            meta = json.loads(meta_file.read_text())
            meta["target"] = str(tmp_path / "identity.md")
            meta_file.write_text(json.dumps(meta), encoding="utf-8")

        args = _adopt_args(
            adopt_names=_names_file(tmp_path, "adopt.txt", ["new.md"]),
            archive_names=_names_file(tmp_path, "archive.txt", ["old.md superseded-by new.md"]),
        )
        with (
            patch(
                "contemplative_agent.cli.adopt._print_system_budget_for_staged",
                side_effect=_rewrite_sidecar,
            ),
            pytest.raises(SystemExit) as exc,
        ):
            _run_adopt(tmp_path, staged, args)
        assert exc.value.code == 1
        assert old.read_text() == "# Old\n", "the predecessor must stay in the store"
        assert not (tmp_path / "identity.md").exists(), "the successor must not be written"
        assert not (skills / ".archive").exists()

    def test_the_archive_never_clobbers_an_earlier_retirement(self, tmp_path):
        skills = tmp_path / "skills"
        archive = skills / ".archive"
        archive.mkdir(parents=True)
        (archive / "old.md").write_text("# An older retirement\n", encoding="utf-8")
        _make_skill(tmp_path, "old.md", "# A different body\n")
        args = _adopt_args(archive_names=_names_file(tmp_path, "archive.txt", ["old.md"]))
        _run_adopt(tmp_path, tmp_path / ".staged", args)
        assert (archive / "old.md").read_text() == "# An older retirement\n"
        assert (archive / "old-2.md").read_text() == "# A different body\n"

    def test_a_sidecar_cannot_name_a_skill_to_archive(self, tmp_path):
        """ADR-0097 D5/D6: the archive set comes from argv and nowhere else.

        The adversary in this module's threat model owns `.staged/`. Adding
        the keys an archive would need to a sidecar must buy them nothing —
        otherwise adoption would stop being a write and nothing else.
        """
        skills = tmp_path / "skills"
        victim = _make_skill(tmp_path, "victim.md", "# Victim\n")
        staged = _stage(tmp_path, [StageItem("new.md", "# New", skills / "new.md")])
        meta_file = staged / "new.md.meta.json"
        meta = json.loads(meta_file.read_text())
        meta.update({"archive": ["victim.md"], "supersedes": "victim.md"})
        meta_file.write_text(json.dumps(meta), encoding="utf-8")

        args = _adopt_args(adopt_names=_names_file(tmp_path, "adopt.txt", ["new.md"]))
        _run_adopt(tmp_path, staged, args)

        assert victim.read_text() == "# Victim\n"
        assert not (skills / ".archive").exists()
        assert "supersedes" not in (skills / "new.md").read_text()

    def test_archive_names_composes_with_yes(self, tmp_path):
        """Not mutually exclusive: it selects store files, not staged ones."""
        skills = tmp_path / "skills"
        old = _make_skill(tmp_path, "old.md", "---\nname: old\n---\n\n# Old\n")
        staged = _stage(
            tmp_path,
            [StageItem("new.md", "---\nname: new\n---\n\n# New\n", skills / "new.md")],
        )
        args = _adopt_args(
            yes=True,
            archive_names=_names_file(tmp_path, "archive.txt", ["old.md superseded-by new.md"]),
        )
        _run_adopt(tmp_path, staged, args)
        assert not old.exists()
        assert "supersedes: old.md" in (skills / "new.md").read_text()

    def test_the_summary_reports_the_archive_count(self, tmp_path, capsys):
        _make_skill(tmp_path, "old.md", "# Old\n")
        args = _adopt_args(archive_names=_names_file(tmp_path, "archive.txt", ["old.md"]))
        _run_adopt(tmp_path, tmp_path / ".staged", args)
        assert "1 archived" in capsys.readouterr().out

    def test_the_budget_reading_subtracts_what_the_archive_removes(self, tmp_path, capsys):
        """The projection must not show a rise the operator will never see."""
        _make_skill(tmp_path, "big.md", "# Big\n" + ("filler words here. " * 400))
        args = _adopt_args(archive_names=_names_file(tmp_path, "archive.txt", ["big.md"]))
        _run_adopt(tmp_path, tmp_path / ".staged", args)
        out = capsys.readouterr().out
        match = re.search(r"≈([\d,]+) tok → ≈([\d,]+) tok after this batch", out)
        assert match, out
        current, projected = (int(g.replace(",", "")) for g in match.groups())
        assert projected < current


class TestOrdinaryAdoptIsUnchanged:
    def test_an_adopt_with_no_archive_names_behaves_as_before(self, tmp_path):
        """Behaviour-neutrality: the archive exit is inert unless asked for."""
        kept = _make_skill(tmp_path, "kept.md", "# Kept\n")
        staged = _stage(tmp_path, [StageItem("new.md", "# New", tmp_path / "skills" / "new.md")])
        args = _adopt_args(adopt_names=_names_file(tmp_path, "adopt.txt", ["new.md"]))
        _run_adopt(tmp_path, staged, args)

        assert kept.read_text() == "# Kept\n"
        assert not (tmp_path / "skills" / ".archive").exists()
        assert (tmp_path / "skills" / "new.md").read_text() == "# New\n"
        assert not (staged / "new.md").exists()
        decisions = [(Path(r["path"]).name, r["decision"]) for r in _audit(tmp_path)]
        assert decisions == [("new.md", "staged"), ("new.md", "approved")]


class TestRemoveSkillArchives:
    @staticmethod
    def _args(name: str, **overrides) -> argparse.Namespace:
        kwargs: dict = {
            "name": name,
            "reason": "superseded at the gate",
            "yes": True,
            "dry_run": False,
            "delete": False,
        }
        kwargs.update(overrides)
        return argparse.Namespace(**kwargs)

    def _run(self, tmp_path: Path, args, *, inputs=None):
        with (
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch(
                "contemplative_agent.cli.approval.AUDIT_LOG_PATH",
                tmp_path / "logs" / "audit.jsonl",
            ),
            patch("builtins.input", side_effect=inputs or []),
        ):
            _handle_remove_skill(args, MagicMock())

    def test_archive_is_the_default_exit(self, tmp_path):
        skill = _make_skill(tmp_path, "stale.md", "# Stale\ncontent\n")
        self._run(tmp_path, self._args("stale"))
        assert not skill.exists()
        assert (tmp_path / "skills" / ".archive" / "stale.md").read_text() == "# Stale\ncontent\n"

    def test_delete_flag_still_deletes(self, tmp_path):
        skill = _make_skill(tmp_path, "stale.md", "# Stale\n")
        self._run(tmp_path, self._args("stale", delete=True))
        assert not skill.exists()
        assert not (tmp_path / "skills" / ".archive").exists()

    def test_the_audit_row_distinguishes_an_archive_from_a_delete(self, tmp_path):
        _make_skill(tmp_path, "a.md", "# A\n")
        _make_skill(tmp_path, "b.md", "# B\n")
        self._run(tmp_path, self._args("a"))
        self._run(tmp_path, self._args("b", delete=True))
        rows = _audit(tmp_path)
        assert [r["command"] for r in rows] == ["remove-skill", "remove-skill"]
        assert Path(rows[0]["path"]).parent.name == ".archive"
        assert Path(rows[1]["path"]).parent.name == "skills"
        assert rows[0]["reason"] == rows[1]["reason"] == "superseded at the gate"

    def test_reason_is_still_mandatory(self, tmp_path):
        skill = _make_skill(tmp_path, "stale.md", "# Stale\n")
        with pytest.raises(SystemExit) as exc:
            self._run(tmp_path, self._args("stale", reason="   "))
        assert exc.value.code == 2
        assert skill.exists()
        assert not _audit(tmp_path)

    def test_the_archive_dir_is_created_lazily(self, tmp_path):
        """No empty `.archive/` in a home that has never retired anything."""
        _make_skill(tmp_path, "stale.md", "# Stale\n")
        assert not (tmp_path / "skills" / ".archive").exists()
        self._run(tmp_path, self._args("stale", dry_run=True))
        assert not (tmp_path / "skills" / ".archive").exists(), "dry-run created the archive"
        self._run(tmp_path, self._args("stale"))
        assert (tmp_path / "skills" / ".archive").is_dir()

    def test_dry_run_refuses_a_symlink_instead_of_promising_an_archive(self, tmp_path, capsys):
        """A dry run must not predict an action the real run will refuse."""
        skills = tmp_path / "skills"
        real = _make_skill(tmp_path, "real.md", "# Real\n")
        (skills / "link.md").symlink_to(real)
        with pytest.raises(SystemExit) as exc:
            self._run(tmp_path, self._args("link", dry_run=True))
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "would archive" not in captured.out
        # Names what the operator typed first, and the referent only as the
        # thing to name instead — the earlier message named the referent alone.
        assert "link.md is a symlink" in captured.err
        assert "Name its referent (real.md)" in captured.err

    def test_dry_run_names_the_archive_destination(self, tmp_path, capsys):
        skill = _make_skill(tmp_path, "stale.md", "# Stale\n")
        self._run(tmp_path, self._args("stale", dry_run=True))
        out = capsys.readouterr().out
        assert "would archive" in out
        assert ".archive/stale.md" in out
        assert skill.exists()
        assert not _audit(tmp_path)

    def test_declining_the_prompt_archives_nothing(self, tmp_path):
        skill = _make_skill(tmp_path, "stale.md", "# Stale\n")
        self._run(tmp_path, self._args("stale", yes=False), inputs=["n"])
        assert skill.exists()
        assert not (tmp_path / "skills" / ".archive").exists()
        assert _audit(tmp_path)[-1]["decision"] == "rejected"

    def test_approving_the_prompt_archives(self, tmp_path, capsys):
        skill = _make_skill(tmp_path, "stale.md", "# Stale\n")
        self._run(tmp_path, self._args("stale", yes=False), inputs=["y"])
        assert not skill.exists()
        assert (tmp_path / "skills" / ".archive" / "stale.md").is_file()
        # The prompt must say what it will do; "Delete …?" would be a lie.
        assert "Archive " in capsys.readouterr().out

    def test_a_symlinked_skill_is_refused_rather_than_moved(self, tmp_path):
        """Moving the link would leave its referent in the store.

        The link points *inside* the store, which is the case the existing
        containment check lets through — a link pointing outside is already
        an exit-2 escape (asserted below).
        """
        skills = tmp_path / "skills"
        real = _make_skill(tmp_path, "real.md", "# Real\n")
        (skills / "link.md").symlink_to(real)
        with pytest.raises(SystemExit) as exc:
            self._run(tmp_path, self._args("link"))
        assert exc.value.code == 1
        assert (skills / "link.md").is_symlink()
        assert real.read_text() == "# Real\n"
        assert not (skills / ".archive").exists()
        assert not _audit(tmp_path)

    def test_delete_never_unlinks_a_symlinks_referent(self, tmp_path, capsys):
        """Silent-failure review 2026-08-22 CRITICAL.

        The symlink refusal used to say "or use --delete to drop the link".
        --delete resolved the leaf, so it unlinked the REFERENT: the operator
        typed `link`, the live skill `real.md` was destroyed with no archive
        and no recovery, and the audit row named a file they never mentioned.
        Under --yes, the documented non-TTY path, nothing intervened.
        """
        skills = tmp_path / "skills"
        real = _make_skill(tmp_path, "real.md", "# Real\n")
        (skills / "link.md").symlink_to(real)
        with pytest.raises(SystemExit) as exc:
            self._run(tmp_path, self._args("link", delete=True))
        assert exc.value.code == 1
        assert real.read_text() == "# Real\n", "the referent must survive"
        assert (skills / "link.md").is_symlink()
        assert not _audit(tmp_path)
        err = capsys.readouterr().err
        assert "symlink" in err
        assert "--delete" not in err, "the message must not recommend what it cannot do"

    def test_a_skill_symlinked_out_of_the_store_is_still_an_escape(self, tmp_path):
        skills = tmp_path / "skills"
        skills.mkdir(parents=True, exist_ok=True)
        outside = tmp_path / "outside.md"
        outside.write_text("# Outside\n", encoding="utf-8")
        (skills / "link.md").symlink_to(outside)
        with pytest.raises(SystemExit) as exc:
            self._run(tmp_path, self._args("link"))
        assert exc.value.code == 2
        assert outside.read_text() == "# Outside\n"

    def test_a_failed_archive_exits_nonzero_with_no_audit_row(self, tmp_path, capsys):
        """Nothing moved, so there is no decision to record — and exit 1."""
        skills = tmp_path / "skills"
        skill = _make_skill(tmp_path, "stale.md", "# Stale\n")
        (skills / ".archive").write_text("not a directory", encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            self._run(tmp_path, self._args("stale"))
        assert exc.value.code == 1
        assert skill.exists()
        # Refused above the prompt, so there is no decision to record.
        assert not _audit(tmp_path)
        assert "ARCHIVE_REFUSED_BAD_DESTINATION" in capsys.readouterr().err

    def test_a_file_already_in_the_archive_has_no_second_exit(self, tmp_path, capsys):
        """Security review 2026-08-22 MEDIUM, first spelling.

        `name` is free-form and `.archive/old.md` resolves inside the skills
        dir, so the containment check admits it. Archiving it again computed
        a destination equal to the source and deleted the last copy while
        exiting 0 with an `approved` audit row.
        """
        skills = tmp_path / "skills"
        archive = skills / ".archive"
        archive.mkdir(parents=True)
        retired = archive / "old.md"
        retired.write_text("# Old\n", encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            self._run(tmp_path, self._args(".archive/old"))
        assert exc.value.code == 1
        assert retired.read_text() == "# Old\n", "the only copy must survive"
        assert not _audit(tmp_path)
        assert "ARCHIVE_REFUSED_ALREADY_ARCHIVED" in capsys.readouterr().err

    def test_purging_from_the_archive_still_needs_an_explicit_delete(self, tmp_path):
        """The escape hatch stays open — deliberate, named, and audited."""
        archive = tmp_path / "skills" / ".archive"
        archive.mkdir(parents=True)
        (archive / "old.md").write_text("# Old\n", encoding="utf-8")
        self._run(tmp_path, self._args(".archive/old", delete=True))
        assert not (archive / "old.md").exists()
        assert _audit(tmp_path)[-1]["decision"] == "approved"

    def test_the_three_retirements_carry_three_audit_sources(self, tmp_path):
        """Silent-failure review HIGH 2: `source` is the discriminator.

        `path` cannot be — a purge from the archive carries an `.archive/`
        path while meaning the opposite of an archive, and the two rows were
        otherwise identical in command, decision, path, hash and run_id.
        """
        _make_skill(tmp_path, "a.md", "# A\n")
        _make_skill(tmp_path, "b.md", "# B\n")
        self._run(tmp_path, self._args("a"))  # archive
        self._run(tmp_path, self._args("b", delete=True))  # delete a live skill
        self._run(tmp_path, self._args(".archive/a", delete=True))  # purge
        sources = [r["source"] for r in _audit(tmp_path)]
        assert sources == ["direct-archive-auto", "direct-remove-auto", "direct-purge-auto"]
        rows = _audit(tmp_path)
        assert Path(rows[0]["path"]).parent.name == Path(rows[2]["path"]).parent.name == ".archive"

    def test_the_interactive_sources_drop_the_auto_suffix(self, tmp_path):
        _make_skill(tmp_path, "a.md", "# A\n")
        self._run(tmp_path, self._args("a", yes=False), inputs=["y"])
        assert _audit(tmp_path)[-1]["source"] == "direct-archive"

    def test_a_failed_unlink_on_the_delete_path_writes_no_row(self, tmp_path):
        """LOW 11: the delete branch logged before unlinking, so a failed
        unlink left a row claiming a deletion that never reached disk."""
        skill = _make_skill(tmp_path, "stale.md", "# Stale\n")
        real_unlink = Path.unlink

        def _refuse(self, *a, **kw):
            if self == skill:
                raise OSError("device busy")
            return real_unlink(self, *a, **kw)

        with patch.object(Path, "unlink", _refuse), pytest.raises(SystemExit) as exc:
            self._run(tmp_path, self._args("stale", delete=True))
        assert exc.value.code == 1
        assert skill.exists()
        assert not _audit(tmp_path), "no row for a deletion that did not happen"

    def test_dry_run_refuses_an_unusable_archive_destination(self, tmp_path, capsys):
        """Codex P2 #2: the preview must not promise what the run refuses."""
        skills = tmp_path / "skills"
        skill = _make_skill(tmp_path, "stale.md", "# Stale\n")
        (skills / ".archive").write_text("not a directory", encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            self._run(tmp_path, self._args("stale", dry_run=True))
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "would archive" not in captured.out
        assert "ARCHIVE_REFUSED_BAD_DESTINATION" in captured.err
        assert skill.exists()

    def test_restoring_an_archived_skill_is_a_plain_mv(self, tmp_path):
        skills = tmp_path / "skills"
        _make_skill(tmp_path, "stale.md", "# Stale\ncontent\n")
        self._run(tmp_path, self._args("stale"))
        (skills / ".archive" / "stale.md").rename(skills / "stale.md")
        assert (skills / "stale.md").read_text() == "# Stale\ncontent\n"
        assert [e.name for e in load_skill_catalog(skills)] == ["stale"]


class TestArchivePlanAgreesWithTheRun:
    """Characterization: `--dry-run` must reach the same verdict as the real run.

    The preview and the move answer the same question from two different
    code paths, and today they agree only because two sets of checks were
    kept in step by hand — a symlink refusal hoisted above the dry run, a
    destination pre-check called twice, an already-in-archive test written
    out twice in one function. This class pins the agreement itself so the
    refactor that turns it into one shared object cannot quietly narrow it.

    Written against the pre-refactor implementation on purpose: a test
    authored after the change would describe the new code rather than the
    behaviour being preserved.
    """

    @staticmethod
    def _build(root: Path, state: str) -> Path:
        """Materialize one store state under a fresh *root*. Returns the root."""
        skills = root / "skills"
        skills.mkdir(parents=True, exist_ok=True)
        if state == "missing":
            return root
        if state == "escapes_store":
            (root / "outside.md").write_text("# Outside\n", encoding="utf-8")
            return root
        if state == "source_is_a_symlink":
            (root / "real.md").write_text("# Real\n", encoding="utf-8")
            (skills / "stale.md").symlink_to(root / "real.md")
            return root
        if state == "source_already_archived":
            archive = skills / ".archive"
            archive.mkdir(parents=True, exist_ok=True)
            (archive / "stale.md").write_text("# Stale\n", encoding="utf-8")
            return root

        (skills / "stale.md").write_text("# Stale\n", encoding="utf-8")
        if state == "archive_is_a_regular_file":
            (skills / ".archive").write_text("not a directory", encoding="utf-8")
        elif state == "archive_symlinks_to_store":
            (skills / ".archive").symlink_to(skills, target_is_directory=True)
        elif state == "name_taken_same_content":
            archive = skills / ".archive"
            archive.mkdir(parents=True, exist_ok=True)
            (archive / "stale.md").write_text("# Stale\n", encoding="utf-8")
        elif state == "name_taken_diff_content":
            archive = skills / ".archive"
            archive.mkdir(parents=True, exist_ok=True)
            (archive / "stale.md").write_text("# A different retirement\n", encoding="utf-8")
        return root

    @staticmethod
    def _name_for(state: str) -> str:
        if state == "escapes_store":
            return "../outside"
        if state == "source_already_archived":
            return ".archive/stale"
        return "stale"

    def _observe(self, root: Path, state: str, *, dry_run: bool, capsys) -> dict:
        """Run one invocation and normalize what an operator would observe."""
        args = TestRemoveSkillArchives._args(self._name_for(state), dry_run=dry_run)
        code = 0
        try:
            TestRemoveSkillArchives()._run(root, args)
        except SystemExit as exc:
            code = exc.code
        captured = capsys.readouterr()
        blob = captured.out + captured.err
        found = re.findall(r"ARCHIVE_REFUSED_[A-Z_]+|ARCHIVE_[A-Z_]+", blob)
        promised = re.search(r"would archive: .* → (\S+)", captured.out)
        rows = _audit(root)

        def _rel(path: Path | None) -> Path | None:
            # The two invocations live under different roots by construction
            # (a fresh store each), so only the path RELATIVE to its own root
            # is comparable.
            return path.relative_to(root) if path is not None else None

        landed = rows[-1]["path"] if rows and rows[-1].get("decision") == "approved" else None
        return {
            "exit": code,
            "reason": found[0] if found else None,
            "promised": _rel(Path(promised.group(1)) if promised else None),
            "landed": _rel(Path(landed) if landed else None),
            "rows": len(rows),
        }

    _STATES = [
        "clean",
        "archive_is_a_regular_file",
        "archive_symlinks_to_store",
        "source_is_a_symlink",
        "source_already_archived",
        "name_taken_same_content",
        "name_taken_diff_content",
        "missing",
        "escapes_store",
    ]

    @pytest.mark.parametrize("state", _STATES)
    def test_the_dry_run_and_the_real_run_reach_the_same_verdict(self, state, tmp_path, capsys):
        dry = self._observe(self._build(tmp_path / "a", state), state, dry_run=True, capsys=capsys)
        real = self._observe(
            self._build(tmp_path / "b", state), state, dry_run=False, capsys=capsys
        )
        assert dry["exit"] == real["exit"], f"{state}: exit codes disagree"
        assert dry["reason"] == real["reason"], f"{state}: reason codes disagree"
        if dry["promised"] is not None:
            assert real["landed"] is not None, f"{state}: promised an archive that did not happen"
            assert dry["promised"].parent == real["landed"].parent, (
                f"{state}: the collision guard may append a suffix, never change directory"
            )

    def test_a_dry_run_never_writes_an_audit_row(self, tmp_path, capsys):
        """The preview is not a decision, so it must leave no record."""
        for state in self._STATES:
            observed = self._observe(
                self._build(tmp_path / state, state), state, dry_run=True, capsys=capsys
            )
            assert observed["rows"] == 0, f"{state}: dry run wrote {observed['rows']} audit row(s)"

    def test_an_archive_symlinked_back_into_the_store_is_refused_by_name_not_by_content(
        self, tmp_path, capsys
    ):
        """Why the dry run has no blind spot here, written down.

        ``ARCHIVE_REFUSED_NOT_A_MOVE`` is the refusal for a destination that
        resolves to its own source, and it is decided late — after the file
        is read, because the collision guard reuses a path only for
        identical bytes. That looks like a case the preview cannot predict,
        since the preview deliberately reads nothing.

        It never gets there. ``.archive`` pointing back at ``skills/`` makes
        every live skill resolve to a path inside the archive, so the
        already-archived refusal fires first — from the resolved *name*
        alone, with no content — and both runs exit 1 with
        ``ARCHIVE_REFUSED_ALREADY_ARCHIVED``.

        Pinned separately from the parametrized agreement above because the
        agreement is the cheap half: what matters is that the refusal is
        reachable without a read. A change that makes NOT_A_MOVE the
        observed outcome would open the blind spot this test says is closed.
        """
        state = "archive_symlinks_to_store"
        dry = self._observe(self._build(tmp_path / "a", state), state, dry_run=True, capsys=capsys)
        real = self._observe(
            self._build(tmp_path / "b", state), state, dry_run=False, capsys=capsys
        )
        assert dry["exit"] == real["exit"] == 1
        assert dry["reason"] == real["reason"] == "ARCHIVE_REFUSED_ALREADY_ARCHIVED"

    def test_a_dangling_symlink_out_of_the_store_reads_as_an_escape(self, tmp_path, capsys):
        """Pins an ordering that looks redundant and is not.

        A link to a deleted file resolves to the referent's path, and that
        path is outside ``skills/`` — so the store-containment gate fires
        first and this exits **2** with "target escapes skills dir", never
        reaching the symlink refusal or the not-found arm. Neither of the
        two reason-coded refusals describes it.

        Recorded because it is the concrete case that makes the handler's
        own containment gate non-redundant with the primitive's: the
        primitive is scoped to the whole data root, where this referent
        still lives, so folding the two together would turn an exit 2 into
        an exit 1 with a reason code that does not apply.
        """
        skills = tmp_path / "skills"
        skills.mkdir(parents=True)
        (skills / "stale.md").symlink_to(tmp_path / "gone.md")
        with pytest.raises(SystemExit) as exc:
            TestRemoveSkillArchives()._run(tmp_path, TestRemoveSkillArchives._args("stale"))
        assert exc.value.code == 2
        assert "escapes skills dir" in capsys.readouterr().err
        assert not _audit(tmp_path)

    def test_delete_ignores_an_unusable_archive_slot(self, tmp_path):
        """`--delete` never touches `.archive/`, so its state cannot block one.

        Untested before this class. A plan/apply split that returned the
        destination refusal as a plain refusal — rather than a field the
        delete arm is free to ignore — would break this silently.
        """
        skills = tmp_path / "skills"
        skill = _make_skill(tmp_path, "stale.md", "# Stale\n")
        (skills / ".archive").write_text("not a directory", encoding="utf-8")
        TestRemoveSkillArchives()._run(
            tmp_path, TestRemoveSkillArchives._args("stale", delete=True)
        )
        assert not skill.exists()
        rows = _audit(tmp_path)
        assert len(rows) == 1 and rows[0]["decision"] == "approved"
