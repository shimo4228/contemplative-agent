"""adopt-staged / remove-skill CLI tests (cli/adopt.py).

Split from the single-file test_cli.py alongside the cli/ package split
(ADR-0079 Phase 2).
"""

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from contemplative_agent.cli.adopt import (
    _AdoptPlan,
    _handle_adopt_staged,
    _handle_remove_skill,
    _hold_one,
    _Outcome,
    _print_system_budget_for_staged,
    _reject_unselected,
    _replaces_canonical_target,
    _report_adopt_outcomes,
    _resolve_adopt_plan,
)
from contemplative_agent.cli.staging import StageItem, _stage_results


class TestHandleRemoveSkill:
    """`remove-skill` CLI: audit-backed manual skill retirement.

    These cover the ``--delete`` path — the irreversible one, unchanged in
    behaviour by ADR-0097 but no longer the default. The archive default and
    its own prompt / audit / containment contracts live in
    ``tests/test_cli_skill_archive.py``.
    """

    @staticmethod
    def _args(
        name: str,
        *,
        reason: str = "obsolete",
        yes: bool = True,
        dry_run: bool = False,
        delete: bool = True,
    ):
        """Build an argparse.Namespace matching the remove-skill subparser."""
        import argparse

        return argparse.Namespace(
            name=name,
            reason=reason,
            yes=yes,
            dry_run=dry_run,
            delete=delete,
        )

    @staticmethod
    def _make_skill(skills_dir: Path, name: str, body: str = "# Skill\ncontent\n") -> Path:
        skills_dir.mkdir(parents=True, exist_ok=True)
        path = skills_dir / f"{name}.md"
        path.write_text(body, encoding="utf-8")
        return path

    def test_removes_skill_with_yes(self, tmp_path):
        skills_dir = tmp_path / "skills"
        target = self._make_skill(skills_dir, "foo-20260417")
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with (
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path),
        ):
            _handle_remove_skill(
                self._args("foo-20260417", reason="old pipeline"),
                MagicMock(),
            )
        assert not target.exists()
        assert not (skills_dir / ".archive").exists(), "--delete must not archive"
        record = json.loads(audit_path.read_text().strip())
        assert record["command"] == "remove-skill"
        assert record["decision"] == "approved"
        assert record["source"] == "direct-remove-auto"
        assert record["reason"] == "old pipeline"
        # The delete row names the path that no longer exists; the archive
        # row names the destination. That contrast is the discriminator
        # (ADR-0097 D5) — pinned from both sides.
        assert Path(record["path"]) == target

    def test_prompts_without_yes_approved(self, tmp_path):
        skills_dir = tmp_path / "skills"
        target = self._make_skill(skills_dir, "bar-20260417")
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with (
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path),
            patch("contemplative_agent.cli.approval._approve_delete", return_value=True),
        ):
            _handle_remove_skill(
                self._args("bar-20260417", yes=False),
                MagicMock(),
            )
        assert not target.exists()
        record = json.loads(audit_path.read_text().strip())
        assert record["source"] == "direct-remove"
        assert record["decision"] == "approved"

    def test_rejects_without_yes(self, tmp_path):
        skills_dir = tmp_path / "skills"
        target = self._make_skill(skills_dir, "baz-20260417")
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with (
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path),
            patch("contemplative_agent.cli.approval._approve_delete", return_value=False),
        ):
            _handle_remove_skill(
                self._args("baz-20260417", yes=False),
                MagicMock(),
            )
        assert target.exists()
        record = json.loads(audit_path.read_text().strip())
        assert record["source"] == "direct-remove"
        assert record["decision"] == "rejected"

    def test_nonexistent_skill_exits(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with (
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path),
        ):
            with pytest.raises(SystemExit) as exc:
                _handle_remove_skill(
                    self._args("nonexistent-20260417"),
                    MagicMock(),
                )
        assert exc.value.code == 1
        assert not audit_path.exists()

    def test_dry_run_skips_delete_and_audit(self, tmp_path, capsys):
        skills_dir = tmp_path / "skills"
        target = self._make_skill(skills_dir, "keep-me-20260417")
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with (
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path),
        ):
            _handle_remove_skill(
                self._args("keep-me-20260417", dry_run=True),
                MagicMock(),
            )
        assert target.exists()
        assert not audit_path.exists()
        out = capsys.readouterr().out
        assert "dry-run" in out
        assert "keep-me-20260417" in out

    def test_reason_required_non_empty(self, tmp_path):
        skills_dir = tmp_path / "skills"
        self._make_skill(skills_dir, "req-20260417")
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with (
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path),
        ):
            with pytest.raises(SystemExit) as exc:
                _handle_remove_skill(
                    self._args("req-20260417", reason="   "),
                    MagicMock(),
                )
        assert exc.value.code == 2

    def test_accepts_name_with_or_without_md(self, tmp_path):
        skills_dir = tmp_path / "skills"
        target = self._make_skill(skills_dir, "ext-20260417")
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with (
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path),
        ):
            _handle_remove_skill(
                self._args("ext-20260417.md"),
                MagicMock(),
            )
        assert not target.exists()

    def test_escape_attempt_rejected(self, tmp_path):
        """Path traversal (../) must be blocked."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (tmp_path / "other.md").write_text("outside", encoding="utf-8")
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with (
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path),
        ):
            with pytest.raises(SystemExit) as exc:
                _handle_remove_skill(
                    self._args("../other"),
                    MagicMock(),
                )
        assert exc.value.code == 2
        assert (tmp_path / "other.md").exists()


class TestAdoptStaged:
    """Tests for `adopt-staged` CLI command (_handle_adopt_staged)."""

    def _stage_one(
        self,
        tmp_path,
        *,
        filename: str,
        text: str,
        target: Path,
        command: str = "insight",
    ) -> Path:
        """Write one staged file + meta.json for the adopt-staged tests."""
        staged_dir = tmp_path / ".staged"
        audit = tmp_path / "logs" / "audit.jsonl"
        item = StageItem(filename, text, target)
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        ):
            _stage_results([item], command=command)
        return staged_dir

    def _run_adopt(self, tmp_path, staged_dir, *, inputs: list[str]):
        audit = tmp_path / "logs" / "audit.jsonl"
        args = argparse.Namespace(yes=False)
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            patch("builtins.input", side_effect=inputs),
        ):
            _handle_adopt_staged(args, MagicMock())

    def test_empty_staging_dir_is_noop(self, tmp_path, capsys):
        staged_dir = tmp_path / ".staged"
        staged_dir.mkdir()
        self._run_adopt(tmp_path, staged_dir, inputs=[])
        out = capsys.readouterr().out
        assert "No staged files." in out

    def test_missing_staging_dir_is_noop(self, tmp_path, capsys):
        staged_dir = tmp_path / ".staged"  # does not exist
        self._run_adopt(tmp_path, staged_dir, inputs=[])
        out = capsys.readouterr().out
        assert "No staging directory." in out

    def test_approve_writes_target_and_clears_staging(self, tmp_path):
        target = tmp_path / "skills" / "a.md"
        staged = self._stage_one(tmp_path, filename="a.md", text="# A", target=target)
        self._run_adopt(tmp_path, staged, inputs=["y"])
        assert target.exists()
        assert target.read_text().startswith("# A")
        # staging cleared
        assert not (staged / "a.md").exists()
        assert not (staged / "a.md.meta.json").exists()

    def test_reject_does_not_write_and_clears_staging(self, tmp_path):
        target = tmp_path / "skills" / "a.md"
        staged = self._stage_one(tmp_path, filename="a.md", text="# A", target=target)
        self._run_adopt(tmp_path, staged, inputs=["n"])
        assert not target.exists()
        # rejected items are also cleared from staging
        assert not (staged / "a.md").exists()
        assert not (staged / "a.md.meta.json").exists()

    def test_adopt_logs_audit_entry(self, tmp_path):
        target = tmp_path / "skills" / "a.md"
        audit = tmp_path / "logs" / "audit.jsonl"
        staged = self._stage_one(tmp_path, filename="a.md", text="# A", target=target)
        self._run_adopt(tmp_path, staged, inputs=["y"])
        lines = audit.read_text().strip().splitlines()
        # stage + stage-adopted, so >= 2 entries
        decisions = [json.loads(line) for line in lines]
        sources = [d["source"] for d in decisions]
        assert "stage" in sources
        assert "stage-adopted" in sources
        adopted = [d for d in decisions if d["source"] == "stage-adopted"]
        assert adopted[-1]["decision"] == "approved"

    def test_adopt_rejects_escaping_target(self, tmp_path, capsys):
        """Tampered meta.json pointing outside MOLTBOOK_HOME must be rejected."""
        staged_dir = tmp_path / ".staged"
        staged_dir.mkdir()
        (staged_dir / "evil.md").write_text("pwned\n")
        (staged_dir / "evil.md.meta.json").write_text(
            json.dumps({"target": "/tmp/evil-adopted.md", "command": "insight"})  # nosec B108 — deliberate attack fixture
        )
        self._run_adopt(tmp_path, staged_dir, inputs=[])
        assert not Path("/tmp/evil-adopted.md").exists()  # nosec B108 — asserts the escape is rejected
        captured = capsys.readouterr()
        assert "escapes MOLTBOOK_HOME" in captured.err
        # Bytes preserved for inspection, but the sidecar is quarantined
        # (renamed .invalid) so a permanently skipped entry stops counting
        # toward the ADR-0074 pending guard instead of blocking all future
        # staging (codex review 2026-07-09).
        assert (staged_dir / "evil.md").exists()
        assert (staged_dir / "evil.md.meta.json.invalid").exists()
        assert not (staged_dir / "evil.md.meta.json").exists()

    def test_adopt_rejects_an_outward_target_that_resolves_back_inside(self, tmp_path, capsys):
        """The containment check must bound what the WRITE touches.

        ``os.replace`` and ``Path.unlink`` act on the literal path — they
        swap or remove the link itself, never the referent — so checking only
        ``target.resolve()`` let a symlink sitting OUTSIDE the store and
        pointing back in pass as "inside", after which the adoption landed
        outside MOLTBOOK_HOME (security review 2026-08-15, reproduced). Same
        literal-versus-resolved mismatch codex found in
        ``_replaces_canonical_target`` on the same day, in the other
        direction.
        """
        home = tmp_path / "home"
        (home / "skills").mkdir(parents=True)
        canonical = home / "skills" / "real.md"
        canonical.write_text("# real\n", encoding="utf-8")
        outside = tmp_path / "outside"
        outside.mkdir()
        decoy = outside / "decoy.md"
        decoy.symlink_to(canonical)

        staged_dir = home / ".staged"
        staged_dir.mkdir()
        (staged_dir / "evil.md").write_text("pwned\n", encoding="utf-8")
        (staged_dir / "evil.md.meta.json").write_text(
            json.dumps({"target": str(decoy), "command": "insight"}), encoding="utf-8"
        )

        audit = home / "logs" / "audit.jsonl"
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", home),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            patch("builtins.input", side_effect=[]),
        ):
            _handle_adopt_staged(argparse.Namespace(yes=False), MagicMock())

        assert "escapes MOLTBOOK_HOME" in capsys.readouterr().err
        assert decoy.is_symlink(), "the write replaced a path outside the store"
        assert canonical.read_text(encoding="utf-8") == "# real\n"

    def test_the_budget_reading_excludes_what_the_loop_will_refuse(self, tmp_path, capsys):
        """The instrument projects what adoption WILL do, so it has to share
        the loop's containment test. It kept its own resolve-only check, so
        an item the loop rejects for escaping MOLTBOOK_HOME was still counted
        in the figure the operator approves against (codex review
        2026-08-15) — the same two-sites-must-agree shape as the previous
        commit's budget projection.
        """
        home = tmp_path / "home"
        (home / "skills").mkdir(parents=True)
        canonical = home / "skills" / "real.md"
        canonical.write_text("# real\n" + ("word " * 400), encoding="utf-8")
        outside = tmp_path / "outside"
        outside.mkdir()
        decoy = outside / "decoy.md"
        decoy.symlink_to(canonical)

        staged_dir = home / ".staged"
        staged_dir.mkdir()
        (staged_dir / "evil.md").write_text("pwned " * 400, encoding="utf-8")
        (staged_dir / "evil.md.meta.json").write_text(
            json.dumps({"target": str(decoy), "command": "insight"}), encoding="utf-8"
        )

        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", home),
        ):
            _print_system_budget_for_staged(list(staged_dir.glob("*.meta.json")), home.resolve())
            with_escaper = capsys.readouterr().out
            _print_system_budget_for_staged([], home.resolve())
            empty = capsys.readouterr().out

        def _projected(out: str) -> str:
            match = re.search(r"→ ≈([\d,]+) tok", out)
            assert match, f"no budget reading in output: {out!r}"
            return match.group(1)

        assert _projected(with_escaper) == _projected(empty)

    def test_adopt_still_accepts_an_ordinary_target_inside_the_store(self, tmp_path):
        """Guard against over-tightening: the normal path must still adopt."""
        skills = tmp_path / "skills"
        target = skills / "plain.md"
        staged = self._stage_one(tmp_path, filename="plain.md", text="# plain", target=target)
        self._run_adopt(tmp_path, staged, inputs=["y"])
        assert target.read_text(encoding="utf-8") == "# plain\n"

    def test_identity_adoption_replaces_the_canonical_file(self, tmp_path):
        """Regression (T-ADOPT-OVERWRITE-TARGETS, 2 live occurrences): the H5
        collision guard exists to stop one generated artifact from silently
        clobbering another, but `distill-identity` and `amend-constitution`
        exist *to* replace their canonical file. Treating that intent as a
        collision minted `identity-2.md` / `contemplative-axioms-2.md`, and
        the runtime reads `identity.md` by fixed path — so the adoption was
        recorded `approved` while the live value layer never changed
        (2026-08-15 Saturday gate; the 2026-08-09 constitution occurrence was
        worse, since the constitution dir is read by glob)."""
        target = tmp_path / "identity.md"
        target.write_text("# old identity", encoding="utf-8")
        staged = self._stage_one(
            tmp_path,
            filename="identity.md",
            text="# new identity",
            target=target,
            command="distill-identity",
        )
        self._run_adopt(tmp_path, staged, inputs=["y"])
        assert target.read_text().startswith("# new identity")
        assert not (tmp_path / "identity-2.md").exists()

    def test_constitution_adoption_replaces_in_place(self, tmp_path):
        """Same intent, and the shape that actually caused harm: the runtime
        concatenates every `*.md` in the constitution dir, so a `-2.md` twin
        injects the old and new constitutions at once."""
        const_dir = tmp_path / "constitution"
        const_dir.mkdir()
        target = const_dir / "contemplative-axioms.md"
        target.write_text("# old axioms", encoding="utf-8")
        staged = self._stage_one(
            tmp_path,
            filename="contemplative-axioms.md",
            text="# new axioms",
            target=target,
            command="amend-constitution",
        )
        self._run_adopt(tmp_path, staged, inputs=["y"])
        assert target.read_text().startswith("# new axioms")
        assert sorted(p.name for p in const_dir.glob("*.md")) == ["contemplative-axioms.md"]

    def test_replacement_audit_path_matches_the_staged_target(self, tmp_path):
        """What made the failure silent: the audit row honestly recorded the
        renamed path, so `staged` (identity.md) and `approved` (identity-2.md)
        pointed at different files for the same content hash — and neither
        shape of the ADR-0093 approval join caught that. Its identity section
        matched on the exact filename, so the `approved` row for
        `identity-2.md` belonged to **no** section and vanished from the join
        entirely, leaving the identity section reading as if only a `staged`
        row existed; the constitution section is directory-shaped, so the
        `contemplative-axioms-2.md` twin lands in the right section and the
        alarm clears on a row that named a different file. Two different blind
        spots, one cause: the record must not be able to diverge from the
        staged target in the first place.

        The read side is closed too as of 2026-08-22 (findings F1.1):
        `_matches_section` now also places an identity row by the command that
        wrote it, and an in-window row matching no section is rendered as a
        residual instead of vanishing (`tests/test_value_layer_approval_join.py`
        :: `test_a_renamed_identity_leaf_still_belongs_to_the_identity_section`,
        `TestUnmatchedRowsAreVisible`). This test still guards the producer:
        the log is append-only, so a diverging record stays wrong forever in
        every future backfill window, whatever the reader can recover."""
        target = tmp_path / "identity.md"
        target.write_text("# old identity", encoding="utf-8")
        staged = self._stage_one(
            tmp_path,
            filename="identity.md",
            text="# new identity",
            target=target,
            command="distill-identity",
        )
        self._run_adopt(tmp_path, staged, inputs=["y"])
        rows = [
            json.loads(line)
            for line in (tmp_path / "logs" / "audit.jsonl").read_text().splitlines()
            if line.strip()
        ]
        by_decision = {r["decision"]: r for r in rows}
        assert by_decision["approved"]["path"] == by_decision["staged"]["path"]
        assert by_decision["approved"]["path"] == str(target)

    def test_the_command_alone_holds_the_guard_at_the_canonical_path(self, tmp_path):
        """The command dimension, pinned where nothing else is holding it.

        Code review 2026-08-15 (mutation-verified): the `skills/identity.md`
        test below passes even against a command-blind predicate, because the
        *location* bound already saves it — so half the threat model was
        unpinned by a green suite. Here the target IS the canonical path, so
        only the command name stands between a tampered sidecar
        (`{"command": "insight", "target": "<root>/identity.md"}`) and an
        in-place overwrite of the live identity."""
        target = tmp_path / "identity.md"
        target.write_text("# a real identity", encoding="utf-8")
        staged = self._stage_one(
            tmp_path,
            filename="identity.md",
            text="# a generated skill",
            target=target,
            command="insight",
        )
        self._run_adopt(tmp_path, staged, inputs=["y"])
        assert target.read_text().startswith("# a real identity")
        assert (tmp_path / "identity-2.md").exists()

    def test_a_non_md_target_in_the_constitution_dir_keeps_the_guard(self, tmp_path):
        """The `.md` suffix check is load-bearing, not decorative.

        The constitution dir holds `.last_constitution_amend` — the ADR-0091
        cadence marker written by `write_run_marker` at the end of a real
        amendment. Without the suffix check a tampered sidecar aimed at it
        would overwrite the marker with staged prose, resetting the amendment
        interval the value-layer due instrument reads (code review
        2026-08-15, mutation-verified: dropping the check passed every test)."""
        const_dir = tmp_path / "constitution"
        const_dir.mkdir()
        marker = const_dir / ".last_constitution_amend"
        marker.write_text("2026-03-28", encoding="utf-8")
        staged = self._stage_one(
            tmp_path,
            filename=".last_constitution_amend",
            text="# staged prose",
            target=marker,
            command="amend-constitution",
        )
        self._run_adopt(tmp_path, staged, inputs=["y"])
        assert marker.read_text().startswith("2026-03-28")

    def test_the_predicate_agrees_with_the_configured_canonical_paths(self):
        """The predicate re-derives `identity.md` and `constitution/` as string
        literals rather than importing `config.IDENTITY_PATH` — deliberately,
        since the constants are import-time and the tests patch
        `MOLTBOOK_DATA_DIR` underneath them. That agreement is otherwise
        implicit: if the canonical location ever moves, the predicate silently
        returns False and adoption regresses to *exactly* the 2026-08-15 shape
        (audit says `approved`, value layer unchanged, nothing errors). Pin it
        (code review 2026-08-15)."""
        from contemplative_agent.adapters.moltbook import config

        root = config.MOLTBOOK_DATA_DIR
        assert _replaces_canonical_target("distill-identity", config.IDENTITY_PATH, root)
        assert _replaces_canonical_target(
            "amend-constitution", config.CONSTITUTION_DIR / "x.md", root
        )

    def test_an_additive_command_targeting_a_same_named_file_elsewhere(self, tmp_path):
        """The "same basename in another directory" case: an `insight` skill
        that happens to slugify to `identity.md` must not clobber whatever
        sits at `skills/identity.md`. (Held by the location bound; the command
        dimension is pinned by the canonical-path test above.)"""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        target = skills_dir / "identity.md"
        target.write_text("# a real skill", encoding="utf-8")
        staged = self._stage_one(
            tmp_path,
            filename="identity.md",
            text="# a different skill",
            target=target,
            command="insight",
        )
        self._run_adopt(tmp_path, staged, inputs=["y"])
        assert target.read_text().startswith("# a real skill")
        assert (skills_dir / "identity-2.md").exists()

    def test_a_replacement_command_pointed_elsewhere_keeps_the_guard(self, tmp_path):
        """The sidecar is user-writable between stage and adopt, so the
        exemption is bounded by location as well as command: `distill-identity`
        may overwrite `identity.md` and nothing else. A tampered meta cannot
        borrow the replacement intent to clobber an arbitrary file."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        target = skills_dir / "victim.md"
        target.write_text("# keep me", encoding="utf-8")
        staged = self._stage_one(
            tmp_path,
            filename="victim.md",
            text="# clobbered",
            target=target,
            command="distill-identity",
        )
        self._run_adopt(tmp_path, staged, inputs=["y"])
        assert target.read_text().startswith("# keep me")
        assert (skills_dir / "victim-2.md").exists()

    def test_a_symlink_aimed_at_the_canonical_file_keeps_the_guard(self, tmp_path):
        """Codex cross-model review 2026-08-15 (proven by execution): the
        predicate must judge the path the write actually lands on. The write
        goes through ``os.replace`` on the *unresolved* target, so a symlinked
        leaf is replaced itself, not its referent — resolving the leaf granted
        the exemption to `skills/victim.md -> ../identity.md`, clobbered that
        out-of-location path, and left `identity.md` untouched while the
        budget reading subtracted the referent's tokens."""
        canonical = tmp_path / "identity.md"
        canonical.write_text("# canonical identity", encoding="utf-8")
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        alias = skills_dir / "victim.md"
        alias.symlink_to(canonical)
        staged = self._stage_one(
            tmp_path,
            filename="victim.md",
            text="# clobbered",
            target=alias,
            command="distill-identity",
        )
        self._run_adopt(tmp_path, staged, inputs=["y"])
        # Neither file takes the write in place: the guard diverts it.
        assert canonical.read_text().startswith("# canonical identity")
        assert alias.is_symlink()
        assert (skills_dir / "victim-2.md").exists()

    def test_budget_reading_subtracts_the_replaced_canonical_file(self, tmp_path, capsys):
        """Same-PR sweep: the budget projection decides whether the existing
        target survives using the same question the write path asks. Fixing
        only the write path would leave the reading projecting a corpus that
        keeps both copies."""

        home = tmp_path / "home"
        home.mkdir()
        target = home / "identity.md"
        target.write_text("b" * 1500, encoding="utf-8")  # 500 tok — replaced
        staged_dir = tmp_path / ".staged"
        staged_dir.mkdir()
        (staged_dir / "identity.md").write_text("c" * 300)  # +100 tok
        (staged_dir / "identity.md.meta.json").write_text(
            json.dumps({"target": str(target), "command": "distill-identity"})
        )
        with patch(
            "contemplative_agent.core.llm.prompting._build_system_prompt",
            return_value="a" * 3000,  # 1000 tok
        ):
            _print_system_budget_for_staged([staged_dir / "identity.md.meta.json"], data_root=home)
        out = capsys.readouterr().out
        assert "≈1,000 tok → ≈600 tok" in out  # +100 and -500

    def test_adopt_prints_system_budget_reading(self, tmp_path, capsys):
        """The adopt gate shows the read-only system-prompt budget projection
        (2026-07-09: a 13-skill batch was approved blind and grew the system
        prompt past the C2 guard)."""
        target = tmp_path / "skills" / "a.md"
        staged = self._stage_one(tmp_path, filename="a.md", text="# A", target=target)
        with patch(
            "contemplative_agent.core.llm.prompting._build_system_prompt",
            return_value="a" * 3000,
        ):
            self._run_adopt(tmp_path, staged, inputs=["y"])
        out = capsys.readouterr().out
        assert "System prompt budget" in out

    def test_budget_reading_skips_targets_outside_data_root(self, tmp_path, capsys):
        """Codex review 2026-07-10 P2: the instrument pre-pass must apply the
        same MOLTBOOK_HOME containment check as _load_staged_item — a
        tampered sidecar (target outside the data root, e.g. a special file)
        must not be read by the budget pass."""

        staged_dir = tmp_path / ".staged"
        staged_dir.mkdir()
        outside = tmp_path / "outside.md"
        outside.write_text("x" * 30000)  # 10K tok if wrongly counted
        (staged_dir / "evil.md").write_text("small")
        (staged_dir / "evil.md.meta.json").write_text(
            json.dumps({"target": str(outside), "command": "insight"})
        )
        with patch(
            "contemplative_agent.core.llm.prompting._build_system_prompt",
            return_value="a" * 3000,  # 1000 tok
        ):
            _print_system_budget_for_staged(
                [staged_dir / "evil.md.meta.json"], data_root=tmp_path / "home"
            )
        out = capsys.readouterr().out
        # Escaping entry skipped entirely: reading stays at the bare prompt.
        assert "≈1,000 tok → ≈1,000 tok" in out

    def test_budget_reading_does_not_subtract_collision_targets(self, tmp_path, capsys):
        """Codex review 2026-07-10 P2: a write whose target exists with
        different content and is NOT in sources gets a `-2.md` suffix on
        adopt — the original survives, so its tokens must not be subtracted."""

        skills_dir = tmp_path / "home" / "skills"
        skills_dir.mkdir(parents=True)
        target = skills_dir / "a.md"
        target.write_text("b" * 1500)  # 500 tok — must NOT be subtracted
        staged_dir = tmp_path / ".staged"
        staged_dir.mkdir()
        (staged_dir / "a.md").write_text("c" * 300)  # +100 tok
        (staged_dir / "a.md.meta.json").write_text(
            json.dumps({"target": str(target), "command": "insight"})
        )
        with patch(
            "contemplative_agent.core.llm.prompting._build_system_prompt",
            return_value="a" * 3000,  # 1000 tok
        ):
            _print_system_budget_for_staged(
                [staged_dir / "a.md.meta.json"], data_root=tmp_path / "home"
            )
        out = capsys.readouterr().out
        assert "≈1,000 tok → ≈1,100 tok" in out  # +100, no -500

    def test_adopt_survives_budget_instrument_failure(self, tmp_path):
        """Degrade, never abort (ADR-0071 invariant): a broken instrument
        must not block the adoption it merely informs."""
        target = tmp_path / "skills" / "a.md"
        staged = self._stage_one(tmp_path, filename="a.md", text="# A", target=target)
        with patch(
            "contemplative_agent.core.llm.system_prompt_budget_reading",
            side_effect=RuntimeError("instrument broke"),
        ):
            self._run_adopt(tmp_path, staged, inputs=["y"])
        assert target.exists()


class TestAdoptStagedYesFlag:
    """Tests for `adopt-staged --yes` non-interactive auto-approval.

    Coding agents (Claude Code, etc.) run the CLI in a non-TTY bash sandbox
    where `input()` returns EOF and rejects everything. The `--yes` flag
    skips the prompts entirely and records adoptions in the audit log with
    `source="stage-adopted-auto"` so they can be distinguished from
    interactively reviewed adoptions.
    """

    def _run_adopt_yes(self, tmp_path, staged_dir):
        audit = tmp_path / "logs" / "audit.jsonl"
        args = argparse.Namespace(yes=True)
        # Patch input() with a sentinel that fails the test if called.
        # If --yes works correctly, the prompt path should never run.
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            patch("builtins.input") as mock_input,
        ):
            _handle_adopt_staged(args, MagicMock())
            mock_input.assert_not_called()

    def test_yes_flag_approves_merge_without_prompt(self, tmp_path):
        target = tmp_path / "skills" / "a.md"
        staged_dir = tmp_path / ".staged"
        item = StageItem("a.md", "# Auto-approved A", target)
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch(
                "contemplative_agent.cli.approval.AUDIT_LOG_PATH",
                tmp_path / "logs" / "audit.jsonl",
            ),
        ):
            _stage_results([item], command="insight")

        self._run_adopt_yes(tmp_path, staged_dir)

        assert target.exists()
        assert target.read_text().startswith("# Auto-approved A")
        # staging cleared
        assert not (staged_dir / "a.md").exists()
        assert not (staged_dir / "a.md.meta.json").exists()

        # Audit log records the adoption with the auto source value
        audit_lines = (tmp_path / "logs" / "audit.jsonl").read_text().strip().splitlines()
        decisions = [json.loads(line) for line in audit_lines]
        adopted = [d for d in decisions if d["source"] == "stage-adopted-auto"]
        assert len(adopted) == 1
        assert adopted[0]["decision"] == "approved"
        assert adopted[0]["command"] == "insight"


class TestAdoptStagedNamesFlag:
    """Tests for `adopt-staged --adopt-names FILE` per-item non-interactive selection.

    T-ADOPT-PERITEM: the y/n pipe workaround for partial adoption depended on
    the iteration order (seq, not packet numbering), consumed no input on
    quarantined items (desync), and destroyed every staged item regardless of
    decision. `--adopt-names` matches staged items by name, verifies all names
    before any destructive operation, and leaves unselected items staged
    unless `--reject-rest` is explicit.
    """

    def _stage_batch(self, tmp_path, items):
        """Stage a batch of StageItems; returns the staging dir."""
        staged_dir = tmp_path / ".staged"
        audit = tmp_path / "logs" / "audit.jsonl"
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        ):
            _stage_results(items, command="insight")
        return staged_dir

    def _run_adopt_names(
        self,
        tmp_path: Path,
        staged_dir,
        names,
        *,
        reject_rest: bool = False,
        yes: bool = False,
        names_file: Path | None = None,
    ):
        if names_file is None:
            names_file = tmp_path / "adopt-names.txt"
            names_file.write_text("".join(f"{n}\n" for n in names), encoding="utf-8")
        audit = tmp_path / "logs" / "audit.jsonl"
        args = argparse.Namespace(yes=yes, adopt_names=str(names_file), reject_rest=reject_rest)
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            patch("builtins.input") as mock_input,
        ):
            _handle_adopt_staged(args, MagicMock())
            mock_input.assert_not_called()

    def _read_audit(self, tmp_path):
        audit = tmp_path / "logs" / "audit.jsonl"
        if not audit.exists():
            return []
        return [json.loads(line) for line in audit.read_text().strip().splitlines()]

    def test_adoption_is_keyed_by_name_not_iteration_order(self, tmp_path):
        """Risk 1 (2026-08-01 gate): seq order (staging order) differs from
        name order — selection must follow the names, not the positions."""
        skills = tmp_path / "skills"
        items = [
            StageItem("z-first.md", "# Z body", skills / "z-first.md"),
            StageItem("m-second.md", "# M body", skills / "m-second.md"),
            StageItem("a-third.md", "# A body", skills / "a-third.md"),
        ]
        staged = self._stage_batch(tmp_path, items)
        self._run_adopt_names(tmp_path, staged, ["a-third.md", "z-first.md"])
        assert (skills / "z-first.md").read_text() == "# Z body\n"
        assert (skills / "a-third.md").read_text() == "# A body\n"
        assert not (skills / "m-second.md").exists()
        # adopted items cleared from staging; unselected one left intact
        assert not (staged / "z-first.md").exists()
        assert not (staged / "a-third.md.meta.json").exists()
        assert (staged / "m-second.md").exists()
        assert (staged / "m-second.md.meta.json").exists()

    def test_unknown_name_aborts_before_any_destruction(self, tmp_path):
        """Risk 2: one unknown name must abort the whole run — no unlink,
        no adoption, no rejection, staging byte-identical."""
        skills = tmp_path / "skills"
        items = [
            StageItem("a.md", "# A", skills / "a.md"),
            StageItem("b.md", "# B", skills / "b.md"),
        ]
        staged = self._stage_batch(tmp_path, items)
        audit_before = self._read_audit(tmp_path)
        with pytest.raises(SystemExit) as exc:
            self._run_adopt_names(tmp_path, staged, ["a.md", "no-such-item.md"])
        assert exc.value.code == 2
        # nothing adopted, staging fully intact
        assert not (skills / "a.md").exists()
        assert (staged / "a.md").exists()
        assert (staged / "a.md.meta.json").exists()
        assert (staged / "b.md").exists()
        assert (staged / "b.md.meta.json").exists()
        # no new audit entries (only the "stage" ones from staging)
        assert self._read_audit(tmp_path) == audit_before

    def test_unknown_name_error_lists_the_names(self, tmp_path, capsys):
        skills = tmp_path / "skills"
        staged = self._stage_batch(tmp_path, [StageItem("a.md", "# A", skills / "a.md")])
        with pytest.raises(SystemExit):
            self._run_adopt_names(tmp_path, staged, ["ghost-1.md", "ghost-2.md"])
        err = capsys.readouterr().err
        assert "ghost-1.md" in err
        assert "ghost-2.md" in err

    def test_unselected_items_left_staged_by_default(self, tmp_path):
        """Default is safe-side: forgetting --reject-rest keeps the rest."""
        skills = tmp_path / "skills"
        items = [
            StageItem("keep.md", "# Keep", skills / "keep.md"),
            StageItem("rest.md", "# Rest", skills / "rest.md"),
        ]
        staged = self._stage_batch(tmp_path, items)
        self._run_adopt_names(tmp_path, staged, ["keep.md"])
        assert (skills / "keep.md").exists()
        assert not (skills / "rest.md").exists()
        assert (staged / "rest.md").exists()
        assert (staged / "rest.md.meta.json").exists()
        # the unselected item got no audit decision (neither adopted nor rejected)
        decisions = self._read_audit(tmp_path)
        rest_decisions = [
            d
            for d in decisions
            if d["source"].startswith("stage-adopted") and d["path"].endswith("rest.md")
        ]
        assert rest_decisions == []

    def test_reject_rest_rejects_unselected(self, tmp_path):
        skills = tmp_path / "skills"
        items = [
            StageItem("keep.md", "# Keep", skills / "keep.md"),
            StageItem("rest.md", "# Rest", skills / "rest.md"),
        ]
        staged = self._stage_batch(tmp_path, items)
        self._run_adopt_names(tmp_path, staged, ["keep.md"], reject_rest=True)
        assert (skills / "keep.md").exists()
        assert not (skills / "rest.md").exists()
        # rejected item removed from staging
        assert not (staged / "rest.md").exists()
        assert not (staged / "rest.md.meta.json").exists()
        # rejection recorded in the audit log with the names-file provenance
        decisions = self._read_audit(tmp_path)
        rest = [
            d
            for d in decisions
            if d["source"] == "stage-adopted-names" and d["path"].endswith("rest.md")
        ]
        assert len(rest) == 1
        assert rest[0]["decision"] == "rejected"

    def test_audit_source_is_stage_adopted_names(self, tmp_path):
        """Per-item selection is transcribed, not prompted: the audit trail
        must record its own provenance (`stage-adopted-names`), never
        masquerade as an interactive `stage-adopted` session and never as
        the blanket `stage-adopted-auto` (2026-08-01 security review C1)."""
        skills = tmp_path / "skills"
        staged = self._stage_batch(tmp_path, [StageItem("a.md", "# A", skills / "a.md")])
        self._run_adopt_names(tmp_path, staged, ["a.md"])
        decisions = self._read_audit(tmp_path)
        sources = [d["source"] for d in decisions]
        assert "stage-adopted-names" in sources
        assert "stage-adopted" not in sources
        assert "stage-adopted-auto" not in sources
        adopted = [d for d in decisions if d["source"] == "stage-adopted-names"]
        assert adopted[-1]["decision"] == "approved"

    def test_adopt_names_and_yes_are_mutually_exclusive(self, tmp_path):
        skills = tmp_path / "skills"
        staged = self._stage_batch(tmp_path, [StageItem("a.md", "# A", skills / "a.md")])
        with pytest.raises(SystemExit) as exc:
            self._run_adopt_names(tmp_path, staged, ["a.md"], yes=True)
        assert exc.value.code == 2
        # nothing happened
        assert not (skills / "a.md").exists()
        assert (staged / "a.md.meta.json").exists()

    def test_reject_rest_requires_adopt_names(self, tmp_path):
        skills = tmp_path / "skills"
        staged = self._stage_batch(tmp_path, [StageItem("a.md", "# A", skills / "a.md")])
        audit = tmp_path / "logs" / "audit.jsonl"
        args = argparse.Namespace(yes=False, adopt_names=None, reject_rest=True)
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        ):
            with pytest.raises(SystemExit) as exc:
                _handle_adopt_staged(args, MagicMock())
        assert exc.value.code == 2
        assert (staged / "a.md.meta.json").exists()

    def test_unreadable_names_file_aborts_untouched(self, tmp_path):
        """Fault column: a missing names file must abort with an error before
        any staged item is touched (no silent fallback to full adoption)."""
        skills = tmp_path / "skills"
        staged = self._stage_batch(tmp_path, [StageItem("a.md", "# A", skills / "a.md")])
        missing = tmp_path / "does-not-exist.txt"
        with pytest.raises(SystemExit) as exc:
            self._run_adopt_names(tmp_path, staged, [], names_file=missing)
        assert exc.value.code == 2
        assert not (skills / "a.md").exists()
        assert (staged / "a.md.meta.json").exists()

    def test_empty_names_file_aborts_untouched(self, tmp_path):
        """An empty selection is a writer bug, never a decision: with
        --reject-rest it would wipe the whole staging queue while logging
        each item as an individually decided rejection (2026-08-01 security
        review C2, reproduced). Abort like the unreadable-file case."""
        skills = tmp_path / "skills"
        staged = self._stage_batch(tmp_path, [StageItem("a.md", "# A", skills / "a.md")])
        with pytest.raises(SystemExit) as exc:
            self._run_adopt_names(tmp_path, staged, [])
        assert exc.value.code == 2
        assert not (skills / "a.md").exists()
        assert (staged / "a.md").exists()
        assert (staged / "a.md.meta.json").exists()

    def test_empty_names_file_with_reject_rest_deletes_nothing(self, tmp_path):
        """The C2 reproduction itself, pinned: empty file + --reject-rest
        must not delete a single staged item nor write any audit decision."""
        skills = tmp_path / "skills"
        staged = self._stage_batch(
            tmp_path,
            [
                StageItem("a.md", "# A", skills / "a.md"),
                StageItem("b.md", "# B", skills / "b.md"),
            ],
        )
        with pytest.raises(SystemExit) as exc:
            self._run_adopt_names(tmp_path, staged, [], reject_rest=True)
        assert exc.value.code == 2
        assert (staged / "a.md.meta.json").exists()
        assert (staged / "b.md.meta.json").exists()
        # staging itself logs decision="staged" rows; the point is that NO
        # adopt/reject decision was recorded by the aborted run.
        decisions = [d for d in self._read_audit(tmp_path) if d["decision"] != "staged"]
        assert decisions == []

    def test_non_utf8_names_file_aborts_untouched(self, tmp_path):
        """UnicodeDecodeError follows the same clean-abort contract as an
        unreadable file (2026-08-01 security review L1)."""
        skills = tmp_path / "skills"
        staged = self._stage_batch(tmp_path, [StageItem("a.md", "# A", skills / "a.md")])
        bad = tmp_path / "bad-names.txt"
        bad.write_bytes(b"\xff\xfe\x00garbage")
        with pytest.raises(SystemExit) as exc:
            self._run_adopt_names(tmp_path, staged, [], names_file=bad)
        assert exc.value.code == 2
        assert (staged / "a.md.meta.json").exists()

    def test_names_with_blank_lines_and_whitespace(self, tmp_path):
        skills = tmp_path / "skills"
        staged = self._stage_batch(tmp_path, [StageItem("a.md", "# A", skills / "a.md")])
        names_file = tmp_path / "adopt-names.txt"
        names_file.write_text("\n  a.md  \n\n", encoding="utf-8")
        self._run_adopt_names(tmp_path, staged, [], names_file=names_file)
        assert (skills / "a.md").exists()


class TestAdoptStagedHoldNames:
    """Tests for `adopt-staged --hold-names FILE` (T-ADOPT-HOLD).

    The gate offers three answers — approve / reject / hold — but the CLI
    carried a dichotomy: items in ``--adopt-names`` versus the rest, whose
    fate ``--reject-rest`` set for ALL of them at once. Holding one item
    therefore meant leaving the entire remainder staged, un-rejected and
    unrecorded, so the next week's staging run hit the ADR-0074 pending
    guard for a reason nothing in the audit trail explained.

    Hold means: left in staging untouched, with a ``decision="held"`` audit
    row (ADR-0012) and a marker on the sidecar so the pending guard can name
    what is blocking it. Held items deliberately still block next week's
    staging (2026-08-15 decision) — the change is that the block is now a
    recorded choice rather than an accident.
    """

    def _stage_batch(self, tmp_path, items, command="insight"):
        staged_dir = tmp_path / ".staged"
        audit = tmp_path / "logs" / "audit.jsonl"
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        ):
            _stage_results(items, command=command)
        return staged_dir

    def _run(
        self,
        tmp_path: Path,
        staged_dir,
        *,
        adopt=None,
        hold=None,
        reject_rest: bool = False,
        yes: bool = False,
    ):
        def _write(names, filename):
            if names is None:
                return None
            path = tmp_path / filename
            path.write_text("".join(f"{n}\n" for n in names), encoding="utf-8")
            return str(path)

        args = argparse.Namespace(
            yes=yes,
            adopt_names=_write(adopt, "adopt-names.txt"),
            hold_names=_write(hold, "hold-names.txt"),
            reject_rest=reject_rest,
        )
        audit = tmp_path / "logs" / "audit.jsonl"
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            patch("builtins.input") as mock_input,
        ):
            _handle_adopt_staged(args, MagicMock())
            mock_input.assert_not_called()

    def _audit(self, tmp_path):
        audit = tmp_path / "logs" / "audit.jsonl"
        if not audit.exists():
            return []
        return [json.loads(line) for line in audit.read_text().strip().splitlines()]

    def _decisions(self, tmp_path):
        """Map target filename -> the last decision recorded for it."""
        out = {}
        for rec in self._audit(tmp_path):
            out[Path(rec["path"]).name] = rec["decision"]
        return out

    def _three_items(self, tmp_path):
        skills = tmp_path / "skills"
        return skills, [
            StageItem("adopt-me.md", "# Adopt", skills / "adopt-me.md"),
            StageItem("hold-me.md", "# Hold", skills / "hold-me.md"),
            StageItem("reject-me.md", "# Reject", skills / "reject-me.md"),
        ]

    def test_adopt_hold_and_reject_coexist_in_one_run(self, tmp_path):
        """The defect this closes: three outcomes, one invocation."""
        skills, items = self._three_items(tmp_path)
        staged = self._stage_batch(tmp_path, items)

        self._run(tmp_path, staged, adopt=["adopt-me.md"], hold=["hold-me.md"], reject_rest=True)

        assert (skills / "adopt-me.md").read_text() == "# Adopt\n"
        assert not (skills / "hold-me.md").exists()
        assert not (skills / "reject-me.md").exists()
        # adopted and rejected leave staging; only the held item stays
        assert not (staged / "adopt-me.md.meta.json").exists()
        assert not (staged / "reject-me.md.meta.json").exists()
        assert (staged / "hold-me.md").read_text() == "# Hold\n"
        assert (staged / "hold-me.md.meta.json").exists()

    def test_each_outcome_is_individually_recorded(self, tmp_path):
        """ADR-0012: reconstruct afterwards how each item was decided."""
        skills, items = self._three_items(tmp_path)
        staged = self._stage_batch(tmp_path, items)

        self._run(tmp_path, staged, adopt=["adopt-me.md"], hold=["hold-me.md"], reject_rest=True)

        assert self._decisions(tmp_path) == {
            "adopt-me.md": "approved",
            "hold-me.md": "held",
            "reject-me.md": "rejected",
        }

    def test_held_row_keeps_the_per_item_provenance(self, tmp_path):
        skills, items = self._three_items(tmp_path)
        staged = self._stage_batch(tmp_path, items)

        self._run(tmp_path, staged, hold=["hold-me.md"], reject_rest=True)

        held = [rec for rec in self._audit(tmp_path) if rec["decision"] == "held"]
        assert len(held) == 1
        assert held[0]["source"] == "stage-adopted-names"
        assert held[0]["path"] == str(skills / "hold-me.md")

    def test_hold_names_alone_needs_no_adopt_names(self, tmp_path):
        """A week where nothing is adopted is a legitimate outcome."""
        skills, items = self._three_items(tmp_path)
        staged = self._stage_batch(tmp_path, items)

        self._run(tmp_path, staged, hold=["hold-me.md"], reject_rest=True)

        assert not skills.exists(), "nothing was adopted, so no target dir"
        assert (staged / "hold-me.md.meta.json").exists()
        assert not (staged / "adopt-me.md.meta.json").exists()

    def test_unheld_unadopted_items_are_still_left_staged_without_reject_rest(self, tmp_path):
        """--reject-rest stays opt-in: forgetting it must not start deleting."""
        skills, items = self._three_items(tmp_path)
        staged = self._stage_batch(tmp_path, items)

        self._run(tmp_path, staged, adopt=["adopt-me.md"], hold=["hold-me.md"])

        assert (skills / "adopt-me.md").exists()
        assert (staged / "hold-me.md.meta.json").exists()
        assert (staged / "reject-me.md.meta.json").exists()
        assert self._decisions(tmp_path)["reject-me.md"] == "staged"

    def test_a_held_item_is_marked_on_its_sidecar(self, tmp_path):
        """The marker is what lets the ADR-0074 pending guard say WHY it is
        refusing: an audit row alone lives in a different file the staging
        run does not read."""
        skills, items = self._three_items(tmp_path)
        staged = self._stage_batch(tmp_path, items)

        self._run(tmp_path, staged, hold=["hold-me.md"], reject_rest=True)

        meta = json.loads((staged / "hold-me.md.meta.json").read_text())
        assert meta["held"] is True
        assert meta["held_at"]
        # the fields the adopt loop needs must survive the rewrite
        assert meta["target"] == str(skills / "hold-me.md")
        assert meta["command"] == "insight"

    def test_a_held_item_can_be_adopted_on_a_later_run(self, tmp_path):
        """Hold is a deferral, not a terminal state."""
        skills, items = self._three_items(tmp_path)
        staged = self._stage_batch(tmp_path, items)
        self._run(tmp_path, staged, hold=["hold-me.md"], reject_rest=True)

        self._run(tmp_path, staged, adopt=["hold-me.md"], reject_rest=True)

        assert (skills / "hold-me.md").read_text() == "# Hold\n"
        decisions = [rec["decision"] for rec in self._audit(tmp_path)]
        assert decisions.count("held") == 1
        assert decisions.count("approved") == 1

    def test_a_symlinked_sidecar_is_refused_rather_than_copied_back(self, tmp_path):
        """Hold is the only outcome that reads a sidecar and writes it back,
        so it is the only one where a symlinked sidecar would copy an outside
        file's bytes into `.staged/` for whoever planted the link to read."""
        skills, items = self._three_items(tmp_path)
        staged = self._stage_batch(tmp_path, items)

        secret = tmp_path / "outside-secret.json"
        secret.write_text(
            json.dumps({"target": str(skills / "hold-me.md"), "command": "insight"}),
            encoding="utf-8",
        )
        sidecar = staged / "hold-me.md.meta.json"
        sidecar.unlink()
        sidecar.symlink_to(secret)

        with pytest.raises(SystemExit) as exc:
            self._run(tmp_path, staged, hold=["hold-me.md"], reject_rest=True)

        assert exc.value.code == 1
        assert sidecar.is_symlink()
        assert "held" not in [rec["decision"] for rec in self._audit(tmp_path)]

    def test_an_unloadable_requested_hold_fails_instead_of_vanishing(self, tmp_path):
        """A hold the operator asked for must not be quarantined away.

        Quarantining renames the sidecar out of the ADR-0074 pending count,
        so a corrupt sidecar would turn "keep this" into a silent removal —
        and the run still exited 0, letting automation read the hold as done
        while the next batch overwrote the staged content (codex review
        2026-08-15).
        """
        _, items = self._three_items(tmp_path)
        staged = self._stage_batch(tmp_path, items)
        (staged / "hold-me.md.meta.json").write_text("{ not json", encoding="utf-8")

        with pytest.raises(SystemExit) as exc:
            self._run(tmp_path, staged, hold=["hold-me.md"], reject_rest=True)

        assert exc.value.code == 1
        assert (staged / "hold-me.md.meta.json").exists(), "the requested hold was destroyed"
        assert not (staged / "hold-me.md.meta.json.invalid").exists()
        assert (staged / "hold-me.md").exists()

    def test_an_unloadable_requested_adopt_fails_instead_of_exiting_zero(self, tmp_path):
        """T-ADOPT-NAMED-SKIP-EXIT: the sibling hole in the adopt branch.

        The operator named this item: "adopt it". The main branch quarantined
        an unloadable sidecar, counted it as a plain ``skipped`` and let the
        run exit 0, so a non-interactive caller read a partially applied
        batch as success — three branches away from the hold path, which
        already exits 1 for exactly this (code review 2026-08-15 round 2).

        Quarantine is still correct here (unlike for a hold): an invalid
        sidecar can never be adopted, and leaving it in place would block
        every future ``--stage`` run via the ADR-0074 pending guard. What
        changes is that the failure is visible in the exit code.
        """
        skills, items = self._three_items(tmp_path)
        staged = self._stage_batch(tmp_path, items)
        (staged / "adopt-me.md.meta.json").write_text("{ not json", encoding="utf-8")

        with pytest.raises(SystemExit) as exc:
            self._run(tmp_path, staged, adopt=["adopt-me.md"], reject_rest=True)

        assert exc.value.code == 1
        assert not (skills / "adopt-me.md").exists(), "nothing should have been written"
        assert (staged / "adopt-me.md.meta.json.invalid").exists()
        assert "approved" not in [rec["decision"] for rec in self._audit(tmp_path)]

    def test_an_unloadable_item_under_yes_also_fails(self, tmp_path):
        """``--yes`` is the documented non-TTY path, so it must signal too.

        ``--yes`` asserts "adopt everything staged", which makes a quarantined
        item just as much a partially applied batch as a named one. The first
        version of this fix exempted ``--yes`` on the theory that one stale
        sidecar would make every auto-approve run fail; review pointed out
        that it cannot recur, because the sidecar is quarantined out of the
        glob on this very run (code review 2026-08-15).
        """
        _, items = self._three_items(tmp_path)
        staged = self._stage_batch(tmp_path, items)
        (staged / "adopt-me.md.meta.json").write_text("{ not json", encoding="utf-8")

        with pytest.raises(SystemExit) as exc:
            self._run(tmp_path, staged, yes=True)

        assert exc.value.code == 1
        assert (staged / "adopt-me.md.meta.json.invalid").exists()
        # …and the very next run is clean: the corrupt sidecar is gone.
        self._run(tmp_path, staged, yes=True)

    def test_a_bare_interactive_run_still_only_skips(self, tmp_path):
        """No ``--yes``, no ``--adopt-names``: nobody asserted anything.

        A human is at the prompt reading the stderr line, so the corrupt
        sidecar stays a quarantined skip rather than a nonzero exit.
        """
        _, items = self._three_items(tmp_path)
        staged = self._stage_batch(tmp_path, items)
        for name in ("hold-me", "reject-me"):
            (staged / f"{name}.md.meta.json").unlink()
            (staged / f"{name}.md").unlink()
        (staged / "adopt-me.md.meta.json").write_text("{ not json", encoding="utf-8")

        # The sole remaining item fails to load, so no prompt is ever reached
        # (the shared runner asserts input() was never called).
        self._run(tmp_path, staged)

        assert (staged / "adopt-me.md.meta.json.invalid").exists()

    def test_the_marker_lands_on_the_snapshot_that_was_audited(self, tmp_path):
        """One read, not two.

        Re-reading the sidecar at mark time let a rewrite between the two
        reads receive the marker while the audit row still described the item
        loaded before it — the file would say held and the row would name a
        different target (codex review 2026-08-15).
        """
        skills, items = self._three_items(tmp_path)
        staged = self._stage_batch(tmp_path, items)
        sidecar = staged / "hold-me.md.meta.json"
        original = json.loads(sidecar.read_text())

        import contemplative_agent.cli.adopt as adopt_mod

        real_mark = adopt_mod._mark_sidecar_held

        def _rewrite_then_mark(meta_file, meta):
            # A concurrent staging writer swaps the sidecar out from under us
            # after the load and before the mark.
            meta_file.write_text(
                json.dumps({"target": "/etc/passwd", "command": "attacker", "seq": 99}),
                encoding="utf-8",
            )
            return real_mark(meta_file, meta)

        with patch.object(adopt_mod, "_mark_sidecar_held", _rewrite_then_mark):
            self._run(tmp_path, staged, hold=["hold-me.md"], reject_rest=True)

        marked = json.loads(sidecar.read_text())
        assert marked["target"] == original["target"]
        assert marked["command"] == original["command"]
        assert marked["seq"] == original["seq"]
        assert marked["held"] is True

        held = [rec for rec in self._audit(tmp_path) if rec["decision"] == "held"]
        assert held[0]["path"] == str(skills / "hold-me.md")

    def test_a_name_in_both_files_aborts_before_any_destruction(self, tmp_path):
        """Adopt and hold are contradictory answers for one item; guessing a
        precedence would silently pick one of the human's two statements."""
        skills, items = self._three_items(tmp_path)
        staged = self._stage_batch(tmp_path, items)
        audit_before = self._audit(tmp_path)

        with pytest.raises(SystemExit) as exc:
            self._run(tmp_path, staged, adopt=["hold-me.md"], hold=["hold-me.md"], reject_rest=True)

        assert exc.value.code == 2
        assert not (skills / "hold-me.md").exists()
        assert (staged / "reject-me.md.meta.json").exists()
        assert self._audit(tmp_path) == audit_before

    def test_unknown_hold_name_aborts_before_any_destruction(self, tmp_path):
        skills, items = self._three_items(tmp_path)
        staged = self._stage_batch(tmp_path, items)
        audit_before = self._audit(tmp_path)

        with pytest.raises(SystemExit) as exc:
            self._run(tmp_path, staged, adopt=["adopt-me.md"], hold=["ghost.md"], reject_rest=True)

        assert exc.value.code == 2
        assert not (skills / "adopt-me.md").exists()
        assert (staged / "adopt-me.md.meta.json").exists()
        assert self._audit(tmp_path) == audit_before

    def test_hold_names_and_yes_are_mutually_exclusive(self, tmp_path):
        skills, items = self._three_items(tmp_path)
        staged = self._stage_batch(tmp_path, items)

        with pytest.raises(SystemExit) as exc:
            self._run(tmp_path, staged, hold=["hold-me.md"], yes=True)

        assert exc.value.code == 2
        assert not (skills / "hold-me.md").exists()

    def test_empty_hold_names_file_aborts_untouched(self, tmp_path):
        """Same contract as --adopt-names: an empty selection is a writer bug,
        and with --reject-rest it would silently wipe the whole queue."""
        skills, items = self._three_items(tmp_path)
        staged = self._stage_batch(tmp_path, items)

        with pytest.raises(SystemExit) as exc:
            self._run(tmp_path, staged, hold=[], reject_rest=True)

        assert exc.value.code == 2
        assert (staged / "reject-me.md.meta.json").exists()

    def _projected_tokens(self, out: str) -> int:
        """Pull the projected figure out of the adopt-gate budget reading."""
        match = re.search(r"→ ≈([\d,]+) tok after this batch", out)
        assert match, f"no budget reading in output: {out!r}"
        return int(match.group(1).replace(",", ""))

    def test_budget_reading_ignores_held_items(self, tmp_path, capsys):
        """A held item does not enter the store, so it must not enter the
        projection either — the reading is what the operator approves against.

        The two arms differ only in the OUTCOME of the same item. Comparing
        "held" against "left out of the names file" instead would pass with
        the feature deleted entirely, since the filter excludes both
        (code review 2026-08-15).
        """

        def _run_batch(root: Path, adopt, hold):
            root.mkdir(exist_ok=True)
            _, items = self._three_items(root)
            staged = self._stage_batch(root, items)
            self._run(root, staged, adopt=adopt, hold=hold, reject_rest=True)
            return self._projected_tokens(capsys.readouterr().out)

        held = _run_batch(tmp_path / "held", ["adopt-me.md"], ["hold-me.md"])
        adopted = _run_batch(tmp_path / "adopted", ["adopt-me.md", "hold-me.md"], None)

        assert held < adopted, "a held item was counted in the projection"

    def test_summary_counts_held_separately(self, tmp_path, capsys):
        skills, items = self._three_items(tmp_path)
        staged = self._stage_batch(tmp_path, items)

        self._run(tmp_path, staged, adopt=["adopt-me.md"], hold=["hold-me.md"], reject_rest=True)

        out = capsys.readouterr().out
        assert "1 adopted" in out
        assert "1 held" in out
        assert "1 rejected" in out


class TestAdoptCanonicalizesFrontmatterName:
    """Weekly 2026-08-08 F1.3: the one-canonical-identity invariant must be
    established at the write boundary (_adopt_write_item), not inherited from
    the producer. Two divergence sources survived at that boundary:

    1. text staged BEFORE extraction-time canonicalization existed (the
       2026-08-01 straddle: staged 00:16 UTC, fix landed 02:05, adopted 02:37)
       was written verbatim with a diverging ``name:``;
    2. a collision rename (`-2` suffix) changed the filename after the
       producer had canonicalized, minting a fresh divergence.
    """

    DIVERGENT = (
        "---\n"
        "name: assume-perfect-adversarial-understanding\n"
        'description: "d"\n'
        "origin: auto-extracted\n"
        "---\n"
        "\n"
        "# Mandating Structural Integrity Axioms\n"
        "\n"
        "body\n"
    )

    def _adopt(self, tmp_path, items):
        staged_dir = tmp_path / ".staged"
        audit = tmp_path / "logs" / "audit.jsonl"
        args = argparse.Namespace(yes=True)
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        ):
            _stage_results(items, command="insight")
            _handle_adopt_staged(args, MagicMock())

    def test_staged_divergent_name_is_canonicalized_at_write(self, tmp_path):
        """Divergence source 1: a pre-canonicalization (or future
        non-canonicalizing producer) body must not enter the store verbatim."""
        target = tmp_path / "skills" / "mandating-structural-integrity-axioms-20260801.md"
        self._adopt(
            tmp_path,
            [
                StageItem(
                    "mandating-structural-integrity-axioms-20260801.md", self.DIVERGENT, target
                )
            ],
        )
        written = target.read_text()
        assert "name: mandating-structural-integrity-axioms\n" in written
        assert "assume-perfect-adversarial-understanding" not in written
        # Heading (human-readable title) survives untouched.
        assert "# Mandating Structural Integrity Axioms" in written

    def test_collision_rename_recanonicalizes_to_final_stem(self, tmp_path):
        """Divergence source 2: the `-2` collision rename happens after the
        producer canonicalized, so the write must re-derive the name from the
        FINAL stem — and the two files must not share a declared name."""
        canonical = '---\nname: dup-skill\ndescription: "d"\n---\n\n# Dup Skill\n\nfirst body\n'
        collider = '---\nname: dup-skill\ndescription: "d"\n---\n\n# Dup Skill\n\nsecond body\n'
        target = tmp_path / "skills" / "dup-skill-20260801.md"
        self._adopt(
            tmp_path,
            [
                StageItem("dup-skill-20260801.md", canonical, target),
                StageItem("dup-skill-20260801.md", collider, target),
            ],
        )
        first = (tmp_path / "skills" / "dup-skill-20260801.md").read_text()
        second = (tmp_path / "skills" / "dup-skill-20260801-2.md").read_text()
        assert "name: dup-skill\n" in first
        assert "name: dup-skill-2\n" in second

    def test_body_without_frontmatter_passes_through_unchanged(self, tmp_path):
        """Normalization, not a gate: identity/constitution-shaped prose and
        legacy bodies without frontmatter are written byte-identical."""
        target = tmp_path / "identity.md"
        self._adopt(tmp_path, [StageItem("identity.md", "I am prose.\n", target)])
        assert target.read_text() == "I am prose.\n"

    def test_audit_log_hashes_the_written_text(self, tmp_path):
        """The audit row must describe the bytes in the durable store, not
        the pre-normalization staged text (replayable-audit-logs)."""
        import hashlib

        target = tmp_path / "skills" / "mandating-structural-integrity-axioms-20260801.md"
        self._adopt(
            tmp_path,
            [
                StageItem(
                    "mandating-structural-integrity-axioms-20260801.md", self.DIVERGENT, target
                )
            ],
        )
        decisions = [
            json.loads(line)
            for line in (tmp_path / "logs" / "audit.jsonl").read_text().strip().splitlines()
        ]
        adopted = [d for d in decisions if d["source"] == "stage-adopted-auto"]
        assert len(adopted) == 1
        written = target.read_text()
        assert adopted[0]["content_hash"] == (hashlib.sha256(written.encode()).hexdigest()[:16])
        # ...and it must NOT be the hash of the pre-normalization staged text.
        assert (
            adopted[0]["content_hash"] != (hashlib.sha256(self.DIVERGENT.encode()).hexdigest()[:16])
        )


class TestAdoptionOrderForCollisionPair:
    """Codex review round-2 P2: adopt-staged must process a collision pair in
    staging order — a plain name sort put dup-2.md.meta.json first ('-' < '.')
    and swapped the pair's final target names."""

    def test_adoption_preserves_staging_order(self, tmp_path):
        staged_dir = tmp_path / ".staged"
        audit = tmp_path / "logs" / "audit.jsonl"
        target = tmp_path / "skills" / "dup.md"
        items = [
            StageItem("dup.md", "# First", target),
            StageItem("dup.md", "# Second", target),
        ]
        ns = argparse.Namespace(yes=True)
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        ):
            _stage_results(items, command="insight")
            _handle_adopt_staged(ns, MagicMock())
        # First staged item keeps the unsuffixed name; the collider gets -2.
        assert (tmp_path / "skills" / "dup.md").read_text() == "# First\n"
        assert (tmp_path / "skills" / "dup-2.md").read_text() == "# Second\n"


class TestAdoptStagedUncoveredFailurePaths:
    """The five branches the suite never reached (2026-08-16 code review HIGH).

    The refactor that split `_handle_adopt_staged` is what makes these cheap:
    `_hold_one` and `_reject_unselected` are now callable in isolation against
    a synthetic `_AdoptPlan`, and `_resolve_adopt_plan` can be driven without
    reaching the loop at all. Before the split every one of them needed the
    whole 303-line function set up around it, which is why none was tested —
    and they are exactly where an equivalence bug in a behaviour-preserving
    refactor would hide, since none of the three `... FAILURES ...` summary
    strings was asserted anywhere.

    A differential harness (30 scenarios, comparing stdout / stderr / exit
    code / full filesystem state including audit.jsonl against the
    pre-refactor module) found them identical. These tests turn that one-off
    result into a standing guard.
    """

    def _plan(self, tmp_path, staged_dir, **overrides):

        kwargs = {
            "meta_files": sorted(staged_dir.glob("*.meta.json")),
            "adopt_names": set(),
            "hold_names": set(),
            "reject_rest": True,
            "yes": False,
            "audit_source": "stage-adopted-names",
            "data_root": tmp_path.resolve(),
        }
        kwargs.update(overrides)
        return _AdoptPlan(**kwargs)

    def _stage_one(self, tmp_path, name="only.md"):
        staged_dir = tmp_path / ".staged"
        audit = tmp_path / "logs" / "audit.jsonl"
        target = tmp_path / "skills" / name
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        ):
            _stage_results([StageItem(name, "# Body", target)], command="insight")
        return staged_dir

    def test_a_failed_reject_unlink_is_a_failure_not_a_rejection(self, tmp_path):
        """REJECT_FAILED: the item is still staged, so it must not count as gone.

        Counting it as `rejected` would tell a non-interactive caller the
        staging queue was cleared while the item still blocks next week's
        batch (ADR-0074 pending guard). No test reached this branch before.
        """

        staged = self._stage_one(tmp_path)
        meta_file = next(staged.glob("*.meta.json"))
        audit = tmp_path / "logs" / "audit.jsonl"
        with (
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            patch.object(Path, "unlink", side_effect=OSError("read-only staging")),
        ):
            outcome = _reject_unselected(meta_file, self._plan(tmp_path, staged))

        assert outcome is _Outcome.REJECT_FAILED
        assert meta_file.exists(), "the reject failed, so the item must still be staged"
        # No REJECTED row. The unlink is deliberately attempted BEFORE the log,
        # so a failed removal never leaves a row claiming the item was rejected
        # while it still sits in staging (2026-08-01 security review H1). The
        # `staged` row from _stage_results above is expected and ignored.
        decisions = [
            json.loads(line)["decision"] for line in audit.read_text().strip().splitlines()
        ]
        assert decisions == ["staged"], decisions

    def test_the_reject_failure_summary_clause_reaches_the_operator(self, tmp_path):
        """The only consumer of REJECT_FAILED, and it was unasserted too.

        `still staged` is the actionable half: the operator has to know the
        item is blocking, not merely that something failed.
        """

        staged = self._stage_one(tmp_path)
        tally = Counter({_Outcome.REJECT_FAILED: 1})
        with pytest.raises(SystemExit) as exc:
            _report_adopt_outcomes(tally, self._plan(tmp_path, staged))
        assert exc.value.code == 1

    def test_an_unloadable_unselected_item_is_quarantined_and_skipped(self, tmp_path):
        """SKIPPED under --reject-rest: nobody asserted this item should exist.

        Distinct from the adopt path, where the same corruption is a FAILURE:
        here the operator did not name the item, so a load failure is not a
        broken promise — but the sidecar still has to leave the pending count.
        """

        staged = self._stage_one(tmp_path)
        meta_file = next(staged.glob("*.meta.json"))
        meta_file.write_text("{ not json", encoding="utf-8")
        with patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path):
            outcome = _reject_unselected(meta_file, self._plan(tmp_path, staged))

        assert outcome is _Outcome.SKIPPED
        assert not meta_file.exists()
        assert meta_file.with_suffix(meta_file.suffix + ".invalid").exists()

    def test_a_hold_whose_marker_write_fails_is_a_hold_failure(self, tmp_path):
        """HOLD_FAILED with a LOADABLE sidecar — the untested half.

        The suite covered the unloadable-sidecar hold failure, which returns
        one branch earlier. This is the other one: the item loaded, the hold
        was attempted, and the marker or the audit row would not write. Both
        halves must keep the item staged and the exit non-zero.
        """

        staged = self._stage_one(tmp_path, "hold-me.md")
        meta_file = next(staged.glob("*.meta.json"))
        plan = self._plan(tmp_path, staged, hold_names={"hold-me.md"})
        with (
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.adopt._hold_staged_item", return_value=False),
        ):
            outcome = _hold_one(meta_file, plan)

        assert outcome is _Outcome.HOLD_FAILED
        assert meta_file.exists(), "a failed hold must not remove the item"

    @pytest.mark.parametrize("make_staging", [False, True], ids=["no-dir", "empty-dir"])
    def test_named_items_with_nothing_staged_abort_rather_than_no_op(self, tmp_path, make_staging):
        """Exit 2: the operator named items that do not exist.

        Both spellings of "nothing staged" have to abort rather than print a
        cheerful `No staged files.` and exit 0 — a names file that matches
        nothing means the caller's model of staging is wrong, and the weekly
        chain treats exit 0 as "the batch was applied".
        """

        staged_dir = tmp_path / ".staged"
        if make_staging:
            staged_dir.mkdir()
        names = tmp_path / "adopt-names.txt"
        names.write_text("ghost.md\n", encoding="utf-8")
        args = argparse.Namespace(
            yes=False, adopt_names=str(names), hold_names=None, reject_rest=False
        )
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            pytest.raises(SystemExit) as exc,
        ):
            _resolve_adopt_plan(args)
        assert exc.value.code == 2


class TestRetiredSidecarKeysAreRefused:
    """ADR-0097: a sidecar written by a retired producer must not be adopted.

    ``action: "drop"`` and ``sources`` lost their handlers with the stocktake
    merge / clean / drop producers. Read as an ordinary write, a drop item
    would be *written* as a `-2.md` twin of the skill it was approved to
    delete, and logged as an approved write — the opposite of the decision.
    """

    def _stage_legacy(self, tmp_path, meta_extra: dict) -> tuple[Path, Path]:
        staged_dir = tmp_path / ".staged"
        staged_dir.mkdir(parents=True)
        skills = tmp_path / "skills"
        skills.mkdir()
        target = skills / "low-q.md"
        target.write_text("# low quality\n", encoding="utf-8")
        (staged_dir / "low-q.md").write_text("# low quality\n", encoding="utf-8")
        meta = {"target": str(target), "command": "skill-stocktake-drop", "seq": 1, **meta_extra}
        (staged_dir / "low-q.md.meta.json").write_text(json.dumps(meta), encoding="utf-8")
        return staged_dir, target

    def _run(self, tmp_path, staged_dir):
        """A refusal is a failure outcome, so the command exits nonzero — a
        non-interactive caller must not read a skipped item as applied."""
        args = argparse.Namespace(yes=True)
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch(
                "contemplative_agent.cli.approval.AUDIT_LOG_PATH",
                tmp_path / "logs" / "audit.jsonl",
            ),
            pytest.raises(SystemExit) as exc,
        ):
            _handle_adopt_staged(args, MagicMock())
        assert exc.value.code == 1

    def test_a_drop_sidecar_is_refused_not_written(self, tmp_path, capsys):
        staged_dir, target = self._stage_legacy(tmp_path, {"action": "drop"})
        self._run(tmp_path, staged_dir)
        err = capsys.readouterr().err
        assert "retired action" in err and "ADR-0097" in err
        # Neither deleted (no handler) nor twinned (no silent write).
        assert target.read_text() == "# low quality\n"
        assert not (target.parent / "low-q-2.md").exists()

    def test_a_sources_sidecar_is_refused_not_written(self, tmp_path, capsys):
        staged_dir, target = self._stage_legacy(tmp_path, {"sources": ["orig.md"]})
        orig = target.parent / "orig.md"
        orig.write_text("# orig\n", encoding="utf-8")
        self._run(tmp_path, staged_dir)
        assert "retired sources" in capsys.readouterr().err
        assert orig.exists(), "a refused item must not delete anything"
        assert not (target.parent / "low-q-2.md").exists()
