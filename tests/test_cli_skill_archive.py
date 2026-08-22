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
        assert Path(row["path"]).parent.name == ".archive"
        assert row["command"] == "adopt-staged"
        assert row["decision"] == "approved"
        assert "ADR-0097 D5 archive exit" in row["reason"]
        # Transcribed from the names file, never prompted — even here, where
        # the run carried no --adopt-names and would otherwise be recorded as
        # an interactive "stage-adopted" session.
        assert row["source"] == "stage-adopted-names"

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
        assert "ARCHIVE_WRITE_FAILED" in captured.err
        assert "0 archived" in captured.out
        assert "1 archive FAILURES" in captured.out

    def test_a_symlinked_store_skill_is_refused_at_the_adopt_gate_too(self, tmp_path):
        """The primitive refuses it, not just `remove-skill`'s pre-check."""
        skills = tmp_path / "skills"
        real = _make_skill(tmp_path, "real.md", "# Real\n")
        (skills / "link.md").symlink_to(real)
        args = _adopt_args(archive_names=_names_file(tmp_path, "archive.txt", ["link.md"]))
        with pytest.raises(SystemExit) as exc:
            _run_adopt(tmp_path, tmp_path / ".staged", args)
        assert exc.value.code == 1
        assert (skills / "link.md").is_symlink()
        assert real.exists()
        assert not (skills / ".archive").exists()

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
        assert not _audit(tmp_path), "nothing moved, so nothing to record"

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

    def test_the_budget_reading_ignores_an_archive_candidate_it_will_refuse(self, tmp_path, capsys):
        """A symlinked candidate is refused, so its body must not be subtracted."""
        skills = tmp_path / "skills"
        real = _make_skill(tmp_path, "real.md", "# Real\n" + ("filler words here. " * 400))
        (skills / "link.md").symlink_to(real)
        args = _adopt_args(archive_names=_names_file(tmp_path, "archive.txt", ["link.md"]))
        with pytest.raises(SystemExit):
            _run_adopt(tmp_path, tmp_path / ".staged", args)
        out = capsys.readouterr().out
        match = re.search(r"≈([\d,]+) tok → ≈([\d,]+) tok after this batch", out)
        assert match, out
        current, projected = (int(g.replace(",", "")) for g in match.groups())
        assert projected == current, "the reading counted a move the loop refuses"

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
        assert "real.md" not in captured.err, "the message must name what the operator typed"

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
        assert not _audit(tmp_path)
        assert "ARCHIVE_WRITE_FAILED" in capsys.readouterr().err

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

    def test_restoring_an_archived_skill_is_a_plain_mv(self, tmp_path):
        skills = tmp_path / "skills"
        _make_skill(tmp_path, "stale.md", "# Stale\ncontent\n")
        self._run(tmp_path, self._args("stale"))
        (skills / ".archive" / "stale.md").rename(skills / "stale.md")
        assert (skills / "stale.md").read_text() == "# Stale\ncontent\n"
        assert [e.name for e in load_skill_catalog(skills)] == ["stale"]
