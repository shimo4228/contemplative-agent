"""scripts/pipeline_run_status.py: the gate's Step 0(a)+(b) in one command (P2-04.13 PR-B)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import pipeline_run_status as prs  # noqa: E402  # pyright: ignore[reportMissingImports]

END = "2026-10-23"


def _audit(home: Path, *events: dict) -> None:
    (home / "logs").mkdir(parents=True, exist_ok=True)
    (home / "logs" / "weekly-pipeline-audit.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8"
    )


def _artifacts(home: Path, skip: tuple[str, ...] = ()) -> None:
    for template in prs.EXPECTED_ARTIFACTS:
        rel = template.format(end=END)
        if rel in skip:
            continue
        (home / rel).parent.mkdir(parents=True, exist_ok=True)
        (home / rel).write_text("x\n")


def _clean_events(run_id: str = f"weekly-{END}-090000") -> list[dict]:
    return [
        {"run_id": run_id, "event": "chain_start"},
        {"run_id": run_id, "event": "stage_result", "stage": "report", "result": "ok"},
        {"run_id": run_id, "event": "chain_end", "result": "ok", "reasons": "none"},
    ]


def test_a_clean_run_with_every_artifact_exits_zero(tmp_path, capsys):
    _artifacts(tmp_path)
    _audit(tmp_path, *_clean_events())
    assert prs.main([END, "--home", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "chain reasons: none" in out and "VERDICT: run completed clean" in out


def test_a_missing_artifact_and_a_failed_stage_are_presented(tmp_path, capsys):
    _artifacts(tmp_path, skip=(f"pipeline/never-selected/never-selected-{END}.json",))
    events = _clean_events()
    events.insert(
        2,
        {"run_id": f"weekly-{END}-090000", "event": "stage_result", "stage": "neverselected",
         "result": "fail", "reason": "NEVER_SELECTED_SCAN_FAIL"},
    )
    events[-1]["reasons"] = "NEVER_SELECTED_SCAN_FAIL"
    _audit(tmp_path, *events)
    assert prs.main([END, "--home", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "MISSING  pipeline/never-selected/" in out
    assert "chain reasons: NEVER_SELECTED_SCAN_FAIL" in out and "PRESENT BEFORE DECIDING" in out


def test_a_run_that_died_before_chain_end_is_presented(tmp_path, capsys):
    _artifacts(tmp_path)
    _audit(tmp_path, *_clean_events()[:2])
    assert prs.main([END, "--home", str(tmp_path)]) == 1
    assert "chain_end MISSING" in capsys.readouterr().out


def test_no_run_at_all_exits_two_and_still_lists_artifacts(tmp_path, capsys):
    _audit(tmp_path)
    assert prs.main([END, "--home", str(tmp_path)]) == 2
    assert "NO RUN for" in capsys.readouterr().out


def test_the_latest_attempt_is_the_one_read(tmp_path, capsys):
    _artifacts(tmp_path)
    old, new = f"weekly-{END}-090000", f"weekly-{END}-101500"
    _audit(tmp_path, {"run_id": old, "event": "chain_start"}, *_clean_events(new))
    assert prs.main([END, "--home", str(tmp_path)]) == 0
    assert f"run_id: {new}  (earlier attempts: {old})" in capsys.readouterr().out


def _skip_event(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "event": "stage_result",
        "stage": "preflight",
        "result": "skipped",
        "reason": "CHAIN_ALREADY_RUNNING",
    }


def test_a_lock_skipped_later_attempt_is_not_the_run_read(tmp_path, capsys):
    # A real chain (still going, no chain_end) and a later second instance that
    # exited on the lock: the verdict is about the real chain, not "died mid-chain".
    _artifacts(tmp_path)
    real, skipped = f"weekly-{END}-090000", f"weekly-{END}-093000"
    _audit(tmp_path, *_clean_events(real), _skip_event(skipped))
    assert prs.main([END, "--home", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert f"run_id: {real}" in out and f"lock-skipped, ran nothing: {skipped}" in out
    assert "died mid-chain" not in out


def test_only_lock_skipped_attempts_are_no_chain_run(tmp_path, capsys):
    _artifacts(tmp_path)
    _audit(tmp_path, _skip_event(f"weekly-{END}-093000"))
    assert prs.main([END, "--home", str(tmp_path)]) == 2
    out = capsys.readouterr().out
    assert "NO CHAIN RUN" in out and "died mid-chain" not in out


def test_the_expected_artifacts_follow_what_the_chain_writes():
    """The table must not drift from weekly-pipeline.sh (the chain's enumeration)."""
    chain = (SCRIPTS / "weekly-pipeline.sh").read_text(encoding="utf-8")
    for template in prs.EXPECTED_ARTIFACTS:
        base = template.rsplit("/", 1)[1]
        # the chain spells the date as $END_DATE or ${END_DATE}
        shapes = {base.replace("{end}", "$END_DATE"), base.replace("{end}", "${END_DATE}")}
        if template.startswith("reports/analysis/weekly-{end}"):
            shapes |= {f'"{base.replace("{end}", "${END_DATE}")}'}
        assert any(shape in chain for shape in shapes), f"chain does not write {template}"
    # and the other direction: every per-week pipeline/<dir>/<name>-$END_DATE.json it writes
    written = set(re.findall(r'pipeline/([a-z-]+)/[a-z-]+-\$END_DATE\.json', chain))
    listed = {t.split("/")[1] for t in prs.EXPECTED_ARTIFACTS if t.startswith("pipeline/")}
    assert written == listed
