"""Acknowledging a prompt-digest divergence instead of re-running the eval.

ADR-0089 amendment (2026-09-19): ``prompt_templates_sha256`` covers every
registry template, so editing an insight prompt reports the baseline STALE
although the eval only measures the comment path. Detection stays wide; the
escape hatch is a recorded human statement. These tests pin what that hatch
may and may not excuse — the failure mode being guarded is an acknowledgement
that quietly covers a real measurement change.

Every case runs against a fake baseline in tmp_path. The approved baselines
in evals/baselines/ are records of what was measured and are never written
by a test.
"""

from __future__ import annotations

import json

import pytest

import evals.check_staleness as cs
from evals.ack import (
    AckError,
    Acknowledgement,
    acknowledged_hashes,
    append_acknowledgement,
    load_acknowledgements,
    sidecar_path,
)
from evals.compare import IncomparableRunsError, compare_runs

BASELINE_NAME = "comment_golden-2026-09-12.json"


def _manifest(**overrides) -> dict:
    m = {
        "target_model": "gemma4:e4b",
        "temperature": 1.3,
        "assets_sha256": "aaa",
        "judge_prompt_sha256": "bbb",
        "prompt_templates_sha256": "old-digest",
        "dataset_sha256": "ccc",
        "injection_regime": "two_pass_selected",
        "sampling": {"num_ctx": 32768},
    }
    m.update(overrides)
    return m


@pytest.fixture
def baseline(tmp_path, monkeypatch):
    """A fake approved baseline that main() will pick up, plus its bytes."""
    path = tmp_path / BASELINE_NAME
    path.write_text(json.dumps({"manifest": _manifest()}), encoding="utf-8")
    monkeypatch.setattr(cs, "BASELINES_DIR", tmp_path)
    return path


def _entry(**overrides) -> Acknowledgement:
    fields = {
        "date": "2026-09-19T00:00:00Z",
        "baseline_hash": "old-digest",
        "acknowledged_hash": "new-digest",
        "changed_prompt_files": ("config/prompts/insight_novelty.md",),
        "reason": "insight path only",
    }
    fields.update(overrides)
    return Acknowledgement(**fields)  # type: ignore[arg-type]


class TestSidecarRecord:
    def test_absent_sidecar_reads_as_no_acknowledgements(self, baseline):
        assert load_acknowledgements(baseline) == ()
        assert acknowledged_hashes(baseline, "old-digest") == frozenset()

    def test_sidecar_sits_beside_the_baseline(self, baseline):
        assert sidecar_path(baseline).name == "comment_golden-2026-09-12.ack.json"

    def test_append_keeps_earlier_entries(self, baseline):
        append_acknowledgement(baseline, _entry())
        append_acknowledgement(baseline, _entry(acknowledged_hash="newer", reason="second"))
        recorded = load_acknowledgements(baseline)
        assert [a.acknowledged_hash for a in recorded] == ["new-digest", "newer"]
        assert acknowledged_hashes(baseline, "old-digest") == frozenset({"new-digest", "newer"})

    def test_entries_recorded_against_another_baseline_digest_are_ignored(self, baseline):
        """An acknowledgement is a claim about a PAIR. Re-approving a baseline
        in place under the same filename must not inherit the old file's
        excuses (security review, 2026-09-19)."""
        append_acknowledgement(baseline, _entry(baseline_hash="a-different-baseline"))
        assert acknowledged_hashes(baseline, "old-digest") == frozenset()

    def test_unknown_file_list_round_trips_as_unknown_not_empty(self, baseline):
        append_acknowledgement(baseline, _entry(changed_prompt_files=None))
        assert load_acknowledgements(baseline)[0].changed_prompt_files is None
        raw = json.loads(sidecar_path(baseline).read_text(encoding="utf-8"))
        assert raw["acknowledgements"][0]["changed_prompt_files"] == "unknown"

    @pytest.mark.parametrize(
        "body",
        [
            "not json at all",
            '["a list, not a record"]',
            '{"acknowledgements": {"not": "a list"}}',
            '{"acknowledgements": ["not an object"]}',
            '{"acknowledgements": [{"date": "x"}]}',
            '{"acknowledgements": [{"date": "x", '
            '"baseline_prompt_templates_sha256": "a", '
            '"acknowledged_prompt_templates_sha256": "b", "reason": "r", '
            '"changed_prompt_files": 7}]}',
        ],
    )
    def test_malformed_sidecar_raises_rather_than_reading_as_empty(self, baseline, body):
        sidecar_path(baseline).write_text(body, encoding="utf-8")
        with pytest.raises(AckError):
            load_acknowledgements(baseline)

    def test_append_refuses_to_overwrite_a_malformed_sidecar(self, baseline):
        sidecar_path(baseline).write_text("corrupt", encoding="utf-8")
        with pytest.raises(AckError):
            append_acknowledgement(baseline, _entry())
        assert sidecar_path(baseline).read_text(encoding="utf-8") == "corrupt"


class TestAcknowledgeCLI:
    def test_prompt_only_divergence_is_recorded(self, baseline, monkeypatch, capsys):
        before = baseline.read_bytes()
        monkeypatch.setattr(
            cs, "current_state", lambda: _manifest(prompt_templates_sha256="new-digest")
        )
        assert cs.main(["--acknowledge", "--reason", "insight prompts only"]) == 0
        recorded = load_acknowledgements(baseline)
        assert len(recorded) == 1
        assert recorded[0].acknowledged_hash == "new-digest"
        assert recorded[0].baseline_hash == "old-digest"
        assert recorded[0].reason == "insight prompts only"
        assert "the baseline itself is unchanged" in capsys.readouterr().out
        assert baseline.read_bytes() == before, "baseline body must never be rewritten"

    def test_another_diverged_field_refuses_and_writes_nothing(self, baseline, monkeypatch, capsys):
        monkeypatch.setattr(
            cs,
            "current_state",
            lambda: _manifest(prompt_templates_sha256="new-digest", target_model="other:9b"),
        )
        assert cs.main(["--acknowledge", "--reason", "x"]) == 1
        out = capsys.readouterr().out
        assert "target_model" in out and "refusing to acknowledge" in out
        assert not sidecar_path(baseline).exists()

    def test_dry_run_prints_and_writes_nothing(self, baseline, monkeypatch, capsys):
        monkeypatch.setattr(
            cs, "current_state", lambda: _manifest(prompt_templates_sha256="new-digest")
        )
        assert cs.main(["--acknowledge", "--reason", "x", "--dry-run"]) == 0
        assert "nothing written" in capsys.readouterr().out
        assert not sidecar_path(baseline).exists()

    def test_dry_run_alone_is_rejected(self, baseline):
        with pytest.raises(SystemExit) as exit_info:
            cs.main(["--dry-run"])
        assert exit_info.value.code != 0

    def test_baseline_without_a_prompt_digest_refuses(self, baseline, monkeypatch, capsys):
        """There would be nothing to bind the record's other end to, and a
        stringified None would be an entry that can never match again."""
        manifest = _manifest()
        del manifest["prompt_templates_sha256"]
        baseline.write_text(json.dumps({"manifest": manifest}), encoding="utf-8")
        monkeypatch.setattr(
            cs, "current_state", lambda: _manifest(prompt_templates_sha256="new-digest")
        )
        assert cs.main(["--acknowledge", "--reason", "x"]) == 1
        assert "no prompt_templates_sha256 to bind to" in capsys.readouterr().out
        assert not sidecar_path(baseline).exists()

    def test_fresh_baseline_records_nothing(self, baseline, monkeypatch, capsys):
        monkeypatch.setattr(cs, "current_state", lambda: _manifest())
        assert cs.main(["--acknowledge", "--reason", "x"]) == 0
        assert "nothing to acknowledge" in capsys.readouterr().out
        assert not sidecar_path(baseline).exists()

    def test_repeat_of_the_same_digest_records_nothing(self, baseline, monkeypatch, capsys):
        monkeypatch.setattr(
            cs, "current_state", lambda: _manifest(prompt_templates_sha256="new-digest")
        )
        append_acknowledgement(baseline, _entry())
        assert cs.main(["--acknowledge", "--reason", "again"]) == 0
        assert "already acknowledged" in capsys.readouterr().out
        assert len(load_acknowledgements(baseline)) == 1

    @pytest.mark.parametrize(
        "argv",
        [["--acknowledge"], ["--acknowledge", "--reason", "   "], ["--reason", "orphan"]],
    )
    def test_reason_and_acknowledge_only_mean_something_together(self, baseline, argv):
        with pytest.raises(SystemExit) as exit_info:
            cs.main(argv)
        assert exit_info.value.code != 0

    def test_corrupt_sidecar_is_cannot_check_not_stale(self, baseline, monkeypatch, capsys):
        monkeypatch.setattr(
            cs, "current_state", lambda: _manifest(prompt_templates_sha256="new-digest")
        )
        sidecar_path(baseline).write_text("corrupt", encoding="utf-8")
        assert cs.main([]) == 2
        assert "cannot check" in capsys.readouterr().out


class TestChangedPromptFileList:
    """The git-derived list a human reads before believing their own reason.

    ``_git`` is stubbed: the point under test is the filter, and driving it
    through real commits would pin the list to whatever the tree happens to
    hold today.
    """

    def _stub(self, monkeypatch, *, added=("sha",), changed=(), untracked=()):
        def fake(*args: str):
            if args[0] == "log":
                return list(added) or None
            if args[0] == "diff":
                return list(changed)
            return list(untracked)

        monkeypatch.setattr(cs, "_git", fake)

    def test_uncommitted_baseline_is_unknown_not_empty(self, baseline, monkeypatch):
        self._stub(monkeypatch, added=())
        assert cs.changed_prompt_files(baseline) is None

    def test_digest_inputs_and_untracked_files_are_listed(self, baseline, monkeypatch):
        registry = cs.hashed_prompt_paths()[0].relative_to(cs.REPO_ROOT).as_posix()
        self._stub(
            monkeypatch, changed=[registry, "config/domain.json"], untracked=["config/prompts/x.md"]
        )
        listed = cs.changed_prompt_files(baseline)
        assert listed is not None
        # config/prompts/x.md does not exist on disk, so it is kept: a path
        # that is gone (or brand new and unreadable) is shown, not dropped.
        assert set(listed) == {registry, "config/domain.json", "config/prompts/x.md"}

    def test_against_a_real_repository(self, tmp_path, monkeypatch):
        """The stubs above pin the filter; this pins the git invocations —
        that ``--diff-filter=A`` finds the baseline's own commit, that the
        diff is taken against the working tree, and that an untracked file
        joins the list."""
        import subprocess

        from evals import run_eval

        root = tmp_path / "repo"
        (root / "config" / "prompts").mkdir(parents=True)
        (root / "evals" / "baselines").mkdir(parents=True)
        # Read the registry stems before REPO_ROOT is redirected below.
        stem, untracked_stem = (p.stem for p in cs.hashed_prompt_paths()[:2])
        (root / "config" / "prompts" / f"{stem}.md").write_text("v1", encoding="utf-8")
        (root / "config" / "domain.json").write_text("{}", encoding="utf-8")
        baseline_file = root / "evals" / "baselines" / BASELINE_NAME
        baseline_file.write_text("{}", encoding="utf-8")

        def run(*args: str) -> None:
            subprocess.run(
                ["git", "-c", "user.email=t@e", "-c", "user.name=t", *args],
                cwd=root,
                check=True,
                capture_output=True,
            )

        run("init", "-q")
        run("add", "-A")
        run("commit", "-qm", "seed")

        monkeypatch.setattr(cs, "REPO_ROOT", root)
        monkeypatch.setattr(run_eval, "REPO_ROOT", root)
        assert cs.changed_prompt_files(baseline_file) == ()

        (root / "config" / "prompts" / f"{stem}.md").write_text("v2", encoding="utf-8")
        # Untracked, and a registry stem: a prompt added but not yet committed
        # is already in the digest, so it must be in the list.
        (root / "config" / "prompts" / f"{untracked_stem}.md").write_text("x", encoding="utf-8")
        (root / "config" / "prompts" / "not-a-registry-field.md").write_text("x", encoding="utf-8")
        assert cs.changed_prompt_files(baseline_file) == tuple(
            sorted([f"config/prompts/{stem}.md", f"config/prompts/{untracked_stem}.md"])
        )

    def test_script_only_prompts_are_filtered_out(self, baseline, monkeypatch):
        """They cannot move the digest, so showing them would be noise in the
        one list the human is supposed to read carefully."""
        from tests.test_packaged_assets import SCRIPT_READ_PROMPTS

        script_only = f"config/prompts/{sorted(SCRIPT_READ_PROMPTS)[0]}.md"
        assert (cs.REPO_ROOT / script_only).is_file()
        self._stub(monkeypatch, changed=[script_only])
        assert cs.changed_prompt_files(baseline) == ()


class TestStalenessAfterAcknowledgement:
    def test_acknowledged_digest_reads_fresh_and_says_why(self, baseline, monkeypatch, capsys):
        monkeypatch.setattr(
            cs, "current_state", lambda: _manifest(prompt_templates_sha256="new-digest")
        )
        assert cs.main([]) == 1, "without the record this digest is plain STALE"
        capsys.readouterr()
        append_acknowledgement(baseline, _entry())
        assert cs.main([]) == 0
        out = capsys.readouterr().out
        assert "by acknowledgement, not by measurement" in out
        assert "2026-09-19T00:00:00Z" in out and "insight path only" in out

    def test_an_entry_for_another_baseline_digest_does_not_make_it_fresh(
        self, baseline, monkeypatch, capsys
    ):
        append_acknowledgement(baseline, _entry(baseline_hash="a-different-baseline"))
        monkeypatch.setattr(
            cs, "current_state", lambda: _manifest(prompt_templates_sha256="new-digest")
        )
        assert cs.main([]) == 1
        assert "STALE" in capsys.readouterr().out

    def test_a_different_digest_is_still_stale(self, baseline, monkeypatch, capsys):
        append_acknowledgement(baseline, _entry())
        monkeypatch.setattr(
            cs, "current_state", lambda: _manifest(prompt_templates_sha256="third-digest")
        )
        assert cs.main([]) == 1
        out = capsys.readouterr().out
        assert "STALE" in out
        assert "--acknowledge" in out, "the stale hint should offer the recorded-judgement route"

    def test_acknowledgement_does_not_excuse_other_fields(self, baseline, monkeypatch, capsys):
        append_acknowledgement(baseline, _entry())
        monkeypatch.setattr(
            cs,
            "current_state",
            lambda: _manifest(prompt_templates_sha256="new-digest", dataset_sha256="moved"),
        )
        assert cs.main([]) == 1
        assert "dataset_sha256" in capsys.readouterr().out


class TestNewestBaselineIgnoresSidecars:
    def test_an_orphaned_sidecar_is_not_mistaken_for_a_baseline(self, tmp_path):
        """A sidecar sorts before its OWN baseline ("a" < "j"), so the case
        that needs the filter is the orphan: the sidecar's baseline was
        deleted or renamed while an older baseline remains, leaving the
        sidecar sorting last."""
        (tmp_path / "comment_golden-2026-08-31.json").write_text("{}")
        sidecar_path(tmp_path / "comment_golden-2026-09-12.json").write_text("{}")
        picked = cs.newest_baseline(tmp_path)
        assert picked is not None and picked.name == "comment_golden-2026-08-31.json"

    def test_a_live_sidecar_does_not_displace_its_baseline(self, tmp_path):
        (tmp_path / BASELINE_NAME).write_text("{}")
        sidecar_path(tmp_path / BASELINE_NAME).write_text("{}")
        picked = cs.newest_baseline(tmp_path)
        assert picked is not None and picked.name == BASELINE_NAME


class TestCompareHonoursAcknowledgements:
    @staticmethod
    def _run(digest: str) -> dict:
        return {
            "schema_version": 1,
            "manifest": {"prompt_templates_sha256": digest},
            "cases": [{"id": "a", "case_verdict": "ADHERENT"}],
        }

    def test_unacknowledged_digest_is_incomparable(self):
        with pytest.raises(IncomparableRunsError, match="prompt_templates_sha256"):
            compare_runs(self._run("old-digest"), self._run("new-digest"))

    def test_acknowledged_digest_compares(self):
        report = compare_runs(
            self._run("old-digest"),
            self._run("new-digest"),
            acknowledged_prompt_hashes=frozenset({"new-digest"}),
        )
        assert report.unchanged == ("a",)

    def test_acknowledgement_does_not_excuse_a_second_field(self):
        baseline = self._run("old-digest")
        current = self._run("new-digest")
        current["manifest"]["target_model"] = "other:9b"
        with pytest.raises(IncomparableRunsError, match="target_model"):
            compare_runs(baseline, current, acknowledged_prompt_hashes=frozenset({"new-digest"}))
