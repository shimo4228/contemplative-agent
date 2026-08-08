"""Baseline staleness detection (evals/check_staleness.py, ADR-0089).

The check is advisory wiring: verify.sh full mode warns when the approved
baseline no longer matches what a run started now would measure. Blocking
is deliberately NOT tested for — staleness must never fail a commit, only
surface the ADR-0089 re-run trigger mechanically.
"""

from __future__ import annotations

import json
import plistlib

import pytest

from evals.check_staleness import deployment_mismatch, divergences, newest_baseline


def _manifest(**overrides) -> dict:
    m = {
        "target_model": "gemma4:e4b",
        "temperature": 1.3,
        "assets_sha256": "aaa",
        "judge_prompt_sha256": "bbb",
        "dataset_sha256": "ccc",
        "injection_regime": "two_pass_selected",
    }
    m.update(overrides)
    return m


def _write_plist(path, env: dict, fmt=plistlib.FMT_XML) -> None:
    """A real plist, written the way launchd would accept it."""
    with path.open("wb") as handle:
        plistlib.dump(
            {"Label": "com.moltbook.agent", "EnvironmentVariables": env},
            handle,
            fmt=fmt,
        )


class TestDivergences:
    def test_fresh_baseline_has_none(self):
        assert divergences(_manifest(), _manifest()) == []

    @pytest.mark.parametrize(
        "field",
        [
            "target_model",
            "temperature",
            "assets_sha256",
            "judge_prompt_sha256",
            "dataset_sha256",
            # ADR-0089 amendment: the 2026-08-06 baseline could not say which
            # injection regime it measured, so a silent switch to two-pass
            # never registered. Promoting the regime from prose to a manifest
            # field is what makes that drift a diff.
            "injection_regime",
        ],
    )
    def test_each_field_is_a_staleness_signal(self, field):
        stale = divergences(_manifest(), _manifest(**{field: "CHANGED"}))
        assert len(stale) == 1
        assert field in stale[0]

    def test_informational_manifest_fields_are_ignored(self):
        # judge_model / samples_per_case are CLI choices, created_at is a
        # timestamp — none of them mean the tree moved under the baseline.
        baseline = _manifest(
            judge_model="claude-sonnet-5", samples_per_case=3, created_at="2026-08-06"
        )
        assert divergences(baseline, _manifest()) == []

    def test_missing_field_in_old_baseline_counts_as_divergence(self):
        baseline = _manifest()
        del baseline["dataset_sha256"]
        stale = divergences(baseline, _manifest())
        assert len(stale) == 1 and "dataset_sha256" in stale[0]


class TestDeploymentMismatch:
    """Tree-vs-deployment, the axis no in-tree hash can cover.

    ADR-0081 enforcement was switched on in a launchd plist; every other
    staleness signal compares the baseline against the repo, so none of them
    could see it.
    """

    ENFORCED = {"PATH": "/usr/bin", "MOLTBOOK_SKILL_SELECTION_ENFORCE": "1"}

    def test_agreement_is_silence(self, tmp_path):
        p = tmp_path / "com.moltbook.agent.plist"
        _write_plist(p, self.ENFORCED)
        assert deployment_mismatch(p, "two_pass_selected") is None

    def test_enforced_deployment_against_full_corpus_pin_is_reported(self, tmp_path):
        """The 2026-08-06 defect, reproduced as a unit."""
        p = tmp_path / "com.moltbook.agent.plist"
        _write_plist(p, self.ENFORCED)
        msg = deployment_mismatch(p, "full_corpus")
        assert msg is not None
        assert "two_pass_selected" in msg and "full_corpus" in msg

    def test_unenforced_deployment_against_two_pass_pin_is_reported(self, tmp_path):
        """The inverse drift — enforcement switched back off under the eval."""
        p = tmp_path / "com.moltbook.agent.plist"
        _write_plist(p, {"PATH": "/usr/bin"})
        msg = deployment_mismatch(p, "two_pass_selected")
        assert msg is not None and "full_corpus_shadow_observed" in msg

    def test_missing_plist_is_silence_not_a_complaint(self, tmp_path):
        # Fresh clone / CI / non-macOS / schedule never installed.
        assert deployment_mismatch(tmp_path / "absent.plist", "two_pass_selected") is None

    def test_non_1_value_reads_as_not_enforced(self, tmp_path):
        # enforcement_enabled() compares against exactly "1"; so does this.
        p = tmp_path / "com.moltbook.agent.plist"
        _write_plist(p, {"MOLTBOOK_SKILL_SELECTION_ENFORCE": "0"})
        assert deployment_mismatch(p, "two_pass_selected") is not None

    def test_neighbouring_key_with_value_1_does_not_imply_enforcement(self, tmp_path):
        """The false negative the first (string-proximity) implementation had.

        With the flag at 0 and any short-named key set to "1" following it,
        a 64-char window after the key matched the *neighbour's* value and
        the detector returned "agrees" — going silent on manual rollback,
        the exact shape it exists to catch. Ordering matters: the decoy must
        come AFTER the key, or the assertion cannot fail either way.
        """
        p = tmp_path / "com.moltbook.agent.plist"
        _write_plist(p, {"MOLTBOOK_SKILL_SELECTION_ENFORCE": "0", "TZ": "1"})
        assert deployment_mismatch(p, "two_pass_selected") is not None

    def test_binary_plist_is_read_not_crashed_on(self, tmp_path):
        """launchd accepts binary plists (plutil -convert binary1, MDM tooling).

        The text-read implementation raised UnicodeDecodeError from outside
        main()'s guard, so it escaped as a traceback and exit 1 — reported as
        STALE, breaking this module's cannot-check-is-never-stale rule.
        """
        p = tmp_path / "com.moltbook.agent.plist"
        _write_plist(p, self.ENFORCED, fmt=plistlib.FMT_BINARY)
        assert deployment_mismatch(p, "two_pass_selected") is None
        assert deployment_mismatch(p, "full_corpus") is not None

    def test_malformed_plist_is_silence_not_a_crash(self, tmp_path):
        p = tmp_path / "com.moltbook.agent.plist"
        p.write_bytes(b"this is not a plist at all")
        assert deployment_mismatch(p, "two_pass_selected") is None

    def test_regime_names_come_from_the_core_constants(self):
        """Binds this module's comparison to skill_selection's vocabulary.

        Without it, renaming a REGIME_* value would make `deployed` never
        equal the pin — a permanent false mismatch with the suite green.
        """
        import evals.check_staleness as cs
        from contemplative_agent.core.skill_selection import (
            REGIME_FULL_CORPUS_SHADOW,
            REGIME_TWO_PASS_SELECTED,
        )

        assert cs.REGIME_TWO_PASS_SELECTED is REGIME_TWO_PASS_SELECTED
        assert cs.REGIME_FULL_CORPUS_SHADOW is REGIME_FULL_CORPUS_SHADOW


class TestNewestBaseline:
    def test_picks_lexicographically_last(self, tmp_path):
        (tmp_path / "comment_golden-2026-08-06.json").write_text("{}")
        (tmp_path / "comment_golden-2026-09-01.json").write_text("{}")
        picked = newest_baseline(tmp_path)
        assert picked is not None and picked.name == "comment_golden-2026-09-01.json"

    def test_only_the_comment_golden_family_is_considered(self, tmp_path):
        # A future Face B baseline must never be compared against the
        # comment dataset this script hashes.
        (tmp_path / "comment_golden-2026-08-06.json").write_text("{}")
        (tmp_path / "post_golden-2026-12-31.json").write_text("{}")
        (tmp_path / "README.json").write_text("{}")
        picked = newest_baseline(tmp_path)
        assert picked is not None and picked.name == "comment_golden-2026-08-06.json"

    def test_empty_dir_returns_none(self, tmp_path):
        assert newest_baseline(tmp_path) is None


class TestMainExitContract:
    """0 = fresh / 1 = stale / 2 = cannot check — mirrored from run_eval."""

    @pytest.fixture(autouse=True)
    def no_deployment_to_compare(self, tmp_path, monkeypatch):
        """Point the deployment check at nothing.

        Without this the exit contract would depend on whether the machine
        running the tests happens to have the agent schedule installed.
        """
        import evals.check_staleness as cs

        monkeypatch.setattr(cs, "LAUNCHD_PLIST_PATH", tmp_path / "absent.plist")

    def test_deployment_mismatch_alone_is_stale(self, tmp_path, monkeypatch, capsys):
        """Baseline matches the tree, but the tree measures a system the
        deployment does not run — a re-run trigger in its own right."""
        import evals.check_staleness as cs

        plist = tmp_path / "com.moltbook.agent.plist"
        _write_plist(plist, {"PATH": "/usr/bin"})
        monkeypatch.setattr(cs, "LAUNCHD_PLIST_PATH", plist)
        monkeypatch.setattr(cs, "BASELINES_DIR", tmp_path)
        state = _manifest()
        (tmp_path / "comment_golden-2026-08-06.json").write_text(json.dumps({"manifest": state}))
        monkeypatch.setattr(cs, "current_state", lambda: state)

        assert cs.main() == 1
        out = capsys.readouterr().out
        assert "no longer reproduces the deployed system" in out
        # The direction of the fix must be unambiguous in the message itself:
        # the instrument follows production, never the reverse. Both
        # remediation directions are named, because a reinstalled plist that
        # dropped the flag is fixed on the deployment side, not the pin.
        assert "The instrument follows production — never the reverse." in out
        assert "fix the deployment" in out and "fix the pin" in out

    def test_no_baseline_is_2_not_1(self, tmp_path, monkeypatch, capsys):
        import evals.check_staleness as cs

        monkeypatch.setattr(cs, "BASELINES_DIR", tmp_path)
        assert cs.main() == 2
        assert "regression gate inactive" in capsys.readouterr().out

    def test_malformed_baseline_is_2_not_1(self, tmp_path, monkeypatch, capsys):
        import evals.check_staleness as cs

        (tmp_path / "comment_golden-2026-08-06.json").write_text('["not a run object"]')
        monkeypatch.setattr(cs, "BASELINES_DIR", tmp_path)
        assert cs.main() == 2
        assert "cannot check" in capsys.readouterr().out

    def test_current_state_failure_is_2_not_1(self, tmp_path, monkeypatch, capsys):
        import evals.check_staleness as cs

        (tmp_path / "comment_golden-2026-08-06.json").write_text('{"manifest": {}}')
        monkeypatch.setattr(cs, "BASELINES_DIR", tmp_path)

        def boom():
            raise RuntimeError("instrument died")

        monkeypatch.setattr(cs, "current_state", boom)
        assert cs.main() == 2
        assert "cannot check" in capsys.readouterr().out
