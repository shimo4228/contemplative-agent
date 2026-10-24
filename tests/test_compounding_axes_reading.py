"""Q2 compounding axes script (P3-01.3): fixture data repo, no real data."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import compounding_axes_reading as car  # noqa: E402  # pyright: ignore[reportMissingImports]


def _repo(tmp_path: Path) -> Path:
    ns = tmp_path / "pipeline" / "never-selected"
    co = tmp_path / "pipeline" / "comment-outcomes"
    ns.mkdir(parents=True)
    co.mkdir(parents=True)
    (ns / "never-selected-2026-10-09.json").write_text(
        json.dumps(
            {
                "catalog": {"size": 20, "available": True},
                "strict": [{"name": "a"}],
                "dormant": [{"name": "b"}, {"name": "c"}],
                "below_floor": [],
            }
        )
    )
    (ns / "never-selected-2026-10-16.json").write_text(
        json.dumps({"catalog": {"size": 5, "available": False}})
    )
    (co / "comment-outcomes-2026-10-16.json").write_text(
        json.dumps(
            {
                "observed_publishes": 8,
                "unobserved_publishes": 2,
                "skills": [
                    {"skill": "s1", "injected_comments": 12, "comments_with_reply": 9},
                    {"skill": "s2", "injected_comments": 3, "comments_with_reply": 3},
                ],
            }
        )
    )
    # 2026-10-05 is a Monday; the 12th is the next Monday; one row has a retired valid_until, one bad date
    rows = [
        {"pattern": "x", "distilled": "2026-10-05T01:00+00:00", "valid_until": None},
        {"pattern": "y", "distilled": "2026-10-07T01:00+00:00", "valid_until": "2026-10-09"},
        {"pattern": "z", "distilled": "2026-10-19T01:00+00:00", "valid_until": None},
        {"pattern": "w", "distilled": "garbage"},
    ]
    (tmp_path / "knowledge.json").write_text(json.dumps(rows))
    return tmp_path


def test_axes_are_separate_and_never_one_scalar(tmp_path: Path) -> None:
    reading = car.build_reading(_repo(tmp_path), [])
    assert set(reading["axes"]) == {
        "skill_selection_activity",
        "corpus_growth",
        "environment_response",
        "source_pattern_age",
    }
    assert reading["single_scalar"] is None


def test_selection_activity_uses_ever_selected_denominator_and_count_only_below_ten(
    tmp_path: Path,
) -> None:
    rows = car.read_skill_selection_activity(_repo(tmp_path), [])
    first = rows[0]
    assert first["ever_selected"] == 19  # 20 - 1 strict - 0 below floor
    assert first["window_active"]["k"] == 17 and first["window_active"]["n"] == 19
    assert first["window_active"]["ci95"] is not None
    assert rows[1]["status"] == "catalog_unavailable"


def test_corpus_growth_weeks_include_empty_weeks_and_prior_cumulative(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    all_rows = car.read_corpus_growth(repo, [])
    rows = [r for r in all_rows if "week_start" in r]
    assert [r["week_start"] for r in rows] == ["2026-10-05", "2026-10-12", "2026-10-19"]
    assert [r["added"] for r in rows] == [2, 0, 1]
    assert rows[0]["added_still_live"] == 1
    assert rows[1]["cumulative_before"] == 2 and rows[2]["cumulative_before"] == 2
    assert rows[0]["added_over_cumulative_before"] is None
    assert all_rows[-1] == {"unreadable_distilled_rows": 1}


def test_environment_response_wilson_and_small_denominator(tmp_path: Path) -> None:
    row = car.read_environment_response(_repo(tmp_path), [])[0]
    pairs = row["skill_comment_pairs_reply_rate"]
    assert (pairs["k"], pairs["n"]) == (12, 15)
    assert pairs["ci95"] == car.wilson_ci(12, 15)
    assert row["skills_with_at_least_10_pairs"] == 1
    small = car._rate(3, 9)
    assert small["rate"] is None and small["ci95"] is None


def test_boundaries_label_intervals(tmp_path: Path) -> None:
    rows = car.read_skill_selection_activity(_repo(tmp_path), ["2026-10-10"])
    assert [r["interval"] for r in rows] == [0, 1]


def test_age_axis_is_declared_not_omitted(tmp_path: Path) -> None:
    age = car.build_reading(_repo(tmp_path), [])["axes"]["source_pattern_age"]
    assert age["status"] == "not_computed" and age["reanalysis"] == "private-rows"


def test_missing_input_abstains_with_reason_and_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert car.main(["--data-repo", str(tmp_path)]) == 2
    assert "reason=" in capsys.readouterr().err


def test_markdown_renders_all_axes(tmp_path: Path) -> None:
    text = car.render_markdown(car.build_reading(_repo(tmp_path), []))
    for head in (
        "skill_selection_activity",
        "corpus_growth",
        "environment_response",
        "source_pattern_age",
    ):
        assert f"## {head}" in text
