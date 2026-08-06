"""Baseline comparison contract (evals/compare.py).

The comparison operates on the eval layer's own normalized run JSON — never
on deepeval's internal TestRun schema — so it survives deepeval upgrades.
Comparability is gated on the manifest: verdict transitions are meaningless
across a change of target model, temperature, judge, prompt assets, or
dataset, and compare must refuse (not silently proceed) in that case.
"""

from __future__ import annotations

import json

import pytest

from evals.compare import (
    COMPARABILITY_FIELDS,
    CompareReport,
    IncomparableRunsError,
    compare_runs,
    load_run,
)


def _manifest(**overrides) -> dict:
    m = {
        "created_at": "2026-08-06T00:00:00+00:00",
        "target_model": "qwen3.5:9b",
        "temperature": 1.3,
        "judge_model": "claude-opus-5",
        "assets_sha256": "aaa",
        "judge_prompt_sha256": "bbb",
        "dataset_sha256": "ccc",
        "samples_per_case": 3,
        "deepeval_version": "4.1.5",
    }
    m.update(overrides)
    return m


def _case(case_id: str, verdict: str) -> dict:
    return {"id": case_id, "axiom": "Emptiness", "kind": "normal", "case_verdict": verdict}


def _run(cases: list[dict], **manifest_overrides) -> dict:
    return {"schema_version": 1, "manifest": _manifest(**manifest_overrides), "cases": cases}


class TestCompareRuns:
    def test_identical_runs_have_no_transitions(self):
        base = _run([_case("a", "ADHERENT"), _case("b", "DRIFTING")])
        report = compare_runs(base, _run([_case("a", "ADHERENT"), _case("b", "DRIFTING")]))
        assert isinstance(report, CompareReport)
        assert report.regressions == ()
        assert report.improvements == ()
        assert report.unchanged == ("a", "b")

    def test_worsened_verdict_is_a_regression(self):
        base = _run([_case("a", "ADHERENT")])
        cur = _run([_case("a", "DEVIANT")])
        report = compare_runs(base, cur)
        assert [(r.case_id, r.before, r.after) for r in report.regressions] == [
            ("a", "ADHERENT", "DEVIANT")
        ]

    def test_improved_verdict_is_not_a_regression(self):
        base = _run([_case("a", "DRIFTING")])
        report = compare_runs(base, _run([_case("a", "ADHERENT")]))
        assert report.regressions == ()
        assert [(r.case_id, r.before, r.after) for r in report.improvements] == [
            ("a", "DRIFTING", "ADHERENT")
        ]

    def test_added_and_removed_cases_are_reported_not_regressions(self):
        base = _run([_case("a", "ADHERENT")])
        report = compare_runs(base, _run([_case("b", "DEVIANT")]))
        assert report.regressions == ()
        assert report.added == ("b",)
        assert report.removed == ("a",)

    def test_malformed_cases_refuse_comparison_not_crash(self):
        base = _run([_case("a", "ADHERENT")])
        missing_key = _run([{"id": "a"}])
        with pytest.raises(IncomparableRunsError, match="case_verdict"):
            compare_runs(base, missing_key)
        typo = _run([_case("a", "ADHERANT")])
        with pytest.raises(IncomparableRunsError, match="unknown verdict"):
            compare_runs(base, typo)
        not_dicts = _run([])
        not_dicts["cases"] = ["x"]
        with pytest.raises(IncomparableRunsError):
            compare_runs(base, not_dicts)

    @pytest.mark.parametrize("field", sorted(COMPARABILITY_FIELDS))
    def test_manifest_mismatch_refuses_comparison(self, field):
        base = _run([_case("a", "ADHERENT")])
        cur = _run([_case("a", "ADHERENT")], **{field: "OTHER"})
        with pytest.raises(IncomparableRunsError, match=field):
            compare_runs(base, cur)

    def test_deepeval_version_is_informational_only(self):
        base = _run([_case("a", "ADHERENT")])
        cur = _run([_case("a", "ADHERENT")], deepeval_version="9.9.9")
        assert compare_runs(base, cur).regressions == ()

    def test_incomplete_case_refuses_comparison(self):
        base = _run([_case("a", "ADHERENT")])
        cur = _run([_case("a", "INCOMPLETE")])
        with pytest.raises(IncomparableRunsError, match="INCOMPLETE"):
            compare_runs(base, cur)
        with pytest.raises(IncomparableRunsError, match="INCOMPLETE"):
            compare_runs(_run([_case("a", "INCOMPLETE")]), base)


class TestLoadRun:
    def test_roundtrip(self, tmp_path):
        run = _run([_case("a", "ADHERENT")])
        path = tmp_path / "run.json"
        path.write_text(json.dumps(run))
        assert load_run(path) == run

    def test_rejects_unknown_schema_version(self, tmp_path):
        run = _run([])
        run["schema_version"] = 99
        path = tmp_path / "run.json"
        path.write_text(json.dumps(run))
        with pytest.raises(IncomparableRunsError, match="schema_version"):
            load_run(path)

    def test_unreadable_or_invalid_file_is_incomparable_not_a_crash(self, tmp_path):
        with pytest.raises(IncomparableRunsError, match="unreadable"):
            load_run(tmp_path / "missing.json")
        bad = tmp_path / "bad.json"
        bad.write_text("{not json")
        with pytest.raises(IncomparableRunsError, match="unreadable"):
            load_run(bad)
