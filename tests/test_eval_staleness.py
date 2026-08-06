"""Baseline staleness detection (evals/check_staleness.py, ADR-0089).

The check is advisory wiring: verify.sh full mode warns when the approved
baseline no longer matches what a run started now would measure. Blocking
is deliberately NOT tested for — staleness must never fail a commit, only
surface the ADR-0089 re-run trigger mechanically.
"""

from __future__ import annotations

import pytest

from evals.check_staleness import divergences, newest_baseline


def _manifest(**overrides) -> dict:
    m = {
        "target_model": "gemma4:e4b",
        "temperature": 1.3,
        "assets_sha256": "aaa",
        "judge_prompt_sha256": "bbb",
        "dataset_sha256": "ccc",
    }
    m.update(overrides)
    return m


class TestDivergences:
    def test_fresh_baseline_has_none(self):
        assert divergences(_manifest(), _manifest()) == []

    @pytest.mark.parametrize(
        "field",
        ["target_model", "temperature", "assets_sha256", "judge_prompt_sha256", "dataset_sha256"],
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
