"""Deterministic core of the RFC-0079 uncovered probe (scripts/uncovered_probe.py).

No cloud judge is called: the judge is a fake. What is pinned is what a wrong
answer would make look right — the four cells map (on, off) the way the RFC
names them, a judge answer that skips a skill or says anything but yes / no is
excluded with a reason code, a resumed stage never asks a recorded call again,
the recheck draw is seeded and capped per cell, a row whose skill block length
changed is not judged, and the summary carries no text.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "uncovered_probe", REPO_ROOT / "scripts" / "uncovered_probe.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mod = _load_module()


@dataclass(frozen=True)
class FakeRow:
    selection_id: str
    situation: str
    logged_selected: tuple[str, ...]


def test_cells_follow_the_rfc_table():
    assert mod.cell_of("yes", "no") == "carried"
    assert mod.cell_of("yes", "yes") == "context"
    assert mod.cell_of("no", "no") == "uncovered"
    assert mod.cell_of("no", "yes") == "inverse"


def test_parse_accepts_yes_no_for_every_skill_case_insensitively():
    answers, reason = mod.parse_yes_no('{"Alpha": "YES", "beta": "no"}', ("alpha", "Beta"))
    assert reason == ""
    assert answers == {"alpha": "yes", "Beta": "no"}


def test_parse_rejects_missing_skill_bad_value_and_prose():
    assert mod.parse_yes_no('{"alpha": "yes"}', ("alpha", "beta")) == (
        None,
        mod.JUDGE_MISSING_SKILL,
    )
    assert mod.parse_yes_no('{"alpha": "same"}', ("alpha",)) == (None, mod.JUDGE_BAD_VALUE)
    assert mod.parse_yes_no("alpha: yes", ("alpha",)) == (None, mod.JUDGE_PARSE)


def test_block_length_check_compares_with_the_recorded_difference():
    gens = {"on1": {"system_chars": 150}, "off1": {"system_chars": 100}}
    assert mod.block_length_ok(gens, "x" * 60, "x" * 10)
    assert not mod.block_length_ok(gens, "x" * 61, "x" * 10)


def _fake_judge(answers: dict[str, str], calls: list[str]):
    def judge(prompt: str):
        calls.append(prompt)
        return json.dumps(answers), {"total_cost_usd": 0.01}

    return judge


def test_run_stage_resumes_without_asking_again(tmp_path: Path):
    rows = {"r1": FakeRow("r1", "<post>", ("alpha",))}
    texts = {"r1": {"on1": "reply on", "off1": "reply off"}}
    calls: list[str] = []
    kwargs = dict(
        judge=_fake_judge({"alpha": "yes"}, calls),
        model="fake",
        skills_fn=lambda names: {n: f"body of {n}" for n in names},
    )
    work = mod.level_work(["r1"], seed=1)
    first = mod.run_stage("level", work, rows, texts, tmp_path, **kwargs)
    second = mod.run_stage("level", work, rows, texts, tmp_path, **kwargs)
    assert first["recorded"] == 2
    assert second == {"recorded": 0, "call_failed": 0, "skipped_done": 2}
    assert len(calls) == 2
    # The comment reaches the judge inside the untrusted frame, never bare text only.
    assert all("reply" in p and "## Reply" in p for p in calls)


def test_relevance_prompt_carries_no_comment(tmp_path: Path):
    rows = {"r1": FakeRow("r1", "<post>", ("alpha",))}
    texts = {"r1": {"on1": "SECRET-ON", "off1": "SECRET-OFF"}}
    calls: list[str] = []
    mod.run_stage(
        "relevance",
        [("r1", None)],
        rows,
        texts,
        tmp_path,
        judge=_fake_judge({"alpha": "no"}, calls),
        model="fake",
        skills_fn=lambda names: {n: "body" for n in names},
    )
    assert calls and "SECRET" not in calls[0]


def test_failed_call_is_not_recorded(tmp_path: Path):
    rows = {"r1": FakeRow("r1", "<post>", ("alpha",))}

    def failing(_prompt: str):
        raise mod.iar.JudgeCallFailed("X")

    counts = mod.run_stage(
        "relevance",
        [("r1", None)],
        rows,
        {},
        tmp_path,
        judge=failing,
        model="fake",
        skills_fn=lambda names: {n: "body" for n in names},
    )
    assert counts["call_failed"] == 1
    assert not (tmp_path / mod.JUDGMENTS).exists()


def test_recheck_draw_is_seeded_and_capped():
    cells = {(f"r{i}", "s"): ("uncovered" if i % 2 else "carried") for i in range(20)}
    a = mod.draw_recheck_plan(cells, per_cell=3, seed=7)
    b = mod.draw_recheck_plan(cells, per_cell=3, seed=7)
    assert a == b
    assert len(a["uncovered"]) == 3 and len(a["carried"]) == 3
    assert a["context"] == [] and a["inverse"] == []


def _write(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def _level(sid: str, key: str | None, answers: dict[str, str] | None, stage: str = "level") -> dict:
    return {
        "selection_id": sid,
        "stage": stage,
        "text_key": key,
        "answers": answers,
        "reason": "",
        "model": "m",
    }


def test_summary_counts_cells_and_carries_no_text(tmp_path: Path):
    out, source = tmp_path / "out", tmp_path / "src"
    _write(
        out / mod.JUDGMENTS,
        [
            _level("r1", "on1", {"a": "no", "b": "yes"}),
            _level("r1", "off1", {"a": "no", "b": "no"}),
            {**_level("r1", None, {"a": "yes", "b": "no"}, stage="relevance")},
            _level("r2", "on1", {"a": "yes"}),
            _level("r2", "off1", {"a": "yes"}),
            {**_level("r2", None, {"a": "no"}, stage="relevance")},
        ],
    )
    _write(
        source / "judgments.jsonl",
        [
            {
                "selection_id": "r1",
                "question": "q2",
                "reason": "",
                "arms": {"a": "same", "b": "on"},
            },
            {"selection_id": "r2", "question": "q2", "reason": "", "arms": {"a": "same"}},
        ],
    )
    summary = mod.summarize(out, source, ["r1", "r2"], {}, seed=1, iterations=200)
    assert summary["pairs"] == 3
    assert {c: v["pairs"] for c, v in summary["cells"].items()} == {
        "carried": 1,
        "context": 1,
        "uncovered": 1,
        "inverse": 0,
    }
    assert summary["q2_by_cell"]["same"] == {
        "carried": 0,
        "context": 1,
        "uncovered": 1,
        "inverse": 0,
    }
    assert summary["uncovered_share_of_q2_same"]["rate"] == 0.5
    assert summary["relevant_share_of_uncovered"]["rate"] == 1.0
    # Irrelevant pairs: r1/b (off said no) and r2/a (off said yes) — the yes floor is 1/2.
    assert summary["yes_floor_off_on_irrelevant"]["rate"] == 0.5
    assert summary["preregistered"]["yes_floor_upper_below_0.2"] is False
    text = json.dumps(summary)
    assert "raw_b64" not in text and "reply" not in text


def test_parse_failure_is_asked_once_more_then_settled(tmp_path: Path):
    rows = {"r1": FakeRow("r1", "<post>", ("alpha",))}
    calls: list[str] = []
    kwargs = dict(
        judge=_fake_judge({"other": "yes"}, calls),  # always misses the skill
        model="fake",
        skills_fn=lambda names: {n: "body" for n in names},
    )
    for _ in range(3):
        mod.run_stage("relevance", [("r1", None)], rows, {}, tmp_path, **kwargs)
    assert len(calls) == mod.MAX_ATTEMPTS
    assert mod.latest(tmp_path)[("r1", "relevance", "")]["reason"] == mod.JUDGE_MISSING_SKILL


def test_a_parsed_record_wins_over_an_earlier_failed_one(tmp_path: Path):
    _write(
        tmp_path / mod.JUDGMENTS,
        [
            {**_level("r1", None, None, stage="relevance"), "reason": mod.JUDGE_PARSE},
            _level("r1", None, {"a": "yes"}, stage="relevance"),
        ],
    )
    assert mod.latest(tmp_path)[("r1", "relevance", "")]["answers"] == {"a": "yes"}


def test_rows_judged_against_different_bodies_are_dropped(tmp_path: Path):
    out, source = tmp_path / "out", tmp_path / "src"
    _write(
        out / mod.JUDGMENTS,
        [
            {**_level("r1", "on1", {"a": "no"}), "skills_sha256": "one"},
            {**_level("r1", "off1", {"a": "no"}), "skills_sha256": "two"},
            {**_level("r2", "on1", {"a": "yes"}), "skills_sha256": "one"},
            {**_level("r2", "off1", {"a": "no"}), "skills_sha256": "one"},
        ],
    )
    _write(source / "judgments.jsonl", [])
    summary = mod.summarize(out, source, ["r1", "r2"], {}, seed=1, iterations=50)
    assert summary["manifest"]["rows_skill_body_mismatch"] == 1
    assert summary["pairs"] == 1


def test_usable_set_is_frozen_by_the_first_full_run_only(tmp_path: Path):
    assert mod.freeze_usable(tmp_path, {"r1": {}}, {}, limit=2) is None
    assert not (tmp_path / mod.USABLE).exists()
    first = mod.freeze_usable(tmp_path, {"r1": {}, "r2": {}}, {"r3": "x"}, limit=0)
    later = mod.freeze_usable(tmp_path, {"r1": {}}, {}, limit=0)
    assert first is not None and later is not None
    assert later["usable"] == ["r1", "r2"] and later["excluded"] == {"r3": "x"}


def test_cells_are_not_readable_when_the_yes_floor_fails(tmp_path: Path):
    out, source = tmp_path / "out", tmp_path / "src"
    _write(
        out / mod.JUDGMENTS,
        [
            _level("r1", "on1", {"a": "yes"}),
            _level("r1", "off1", {"a": "yes"}),
            _level("r1", None, {"a": "no"}, stage="relevance"),
        ],
    )
    _write(source / "judgments.jsonl", [])
    summary = mod.summarize(out, source, ["r1"], {}, seed=1, iterations=50)
    assert summary["readable"]["cells_readable"] is False
