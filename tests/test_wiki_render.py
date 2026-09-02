"""RFC-0017 S1: the two derived pages the Proposer reads, drawn by code.

Both are read-only projections over logs the loop already writes, so the
tests fix three things: the join (what a row means), the tolerance (a broken
line is counted and skipped, never fatal — the ``observed_injection_outcomes``
posture), and the empty case (a heading, not an empty string).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from contemplative_agent.core import wiki_render


def _write_jsonl(path: Path, rows: list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(r if isinstance(r, str) else json.dumps(r) for r in rows) + "\n",
        encoding="utf-8",
    )


@pytest.fixture()
def data_root(tmp_path: Path) -> Path:
    (tmp_path / "logs").mkdir()
    return tmp_path


# ------------------------------------------------------------ evolution log


def test_evolution_log_is_a_heading_when_nothing_was_ever_staged(data_root: Path) -> None:
    out = wiki_render.render_evolution_log(data_root)
    assert out.strip()
    assert "0" in out
    assert out == wiki_render.render_evolution_log(data_root)


def test_evolution_log_joins_staged_candidates_to_their_final_decision(data_root: Path) -> None:
    _write_jsonl(
        data_root / "logs" / "insight-staged.jsonl",
        [
            {
                "ts": "2026-08-01T00:00+00:00",
                "name": "reply-fast",
                "description": "d1",
                "filename": "reply-fast.md",
            },
            {
                "ts": "2026-08-02T00:00+00:00",
                "name": "upvote-shape",
                "description": "d2",
                "filename": "upvote-shape.md",
            },
        ],
    )
    _write_jsonl(
        data_root / "logs" / "audit.jsonl",
        [
            {
                "ts": "2026-08-01T00:00:01+00:00",
                "command": "insight",
                "path": "/x/.staged/reply-fast.md",
                "decision": "staged",
                "source": "direct",
                "reason": None,
            },
            {
                "ts": "2026-08-03T00:00:00+00:00",
                "command": "adopt-staged",
                "path": "/x/skills/reply-fast.md",
                "decision": "approved",
                "source": "staged_sidecar",
                "reason": None,
            },
            {
                "ts": "2026-08-03T00:00:01+00:00",
                "command": "adopt-staged",
                "path": "/x/skills/upvote-shape.md",
                "decision": "rejected",
                "source": "staged_sidecar",
                "reason": "covered",
            },
        ],
    )

    out = wiki_render.render_evolution_log(data_root)
    rows = [line for line in out.splitlines() if "reply-fast" in line or "upvote-shape" in line]

    assert len(rows) == 2
    assert "2026-08-01" in rows[0] and "approved" in rows[0]
    assert "2026-08-02" in rows[1] and "rejected" in rows[1]
    assert "2" in out


def test_evolution_log_reports_the_latest_decision_not_the_first(data_root: Path) -> None:
    _write_jsonl(
        data_root / "logs" / "insight-staged.jsonl",
        [{"ts": "2026-08-01T00:00+00:00", "name": "a", "description": "", "filename": "a.md"}],
    )
    _write_jsonl(
        data_root / "logs" / "audit.jsonl",
        [
            {"ts": "2026-08-05T00:00:00+00:00", "path": "/x/a.md", "decision": "approved"},
            {"ts": "2026-08-02T00:00:00+00:00", "path": "/x/a.md", "decision": "held"},
        ],
    )
    out = wiki_render.render_evolution_log(data_root)
    row = next(line for line in out.splitlines() if line.startswith("2026-08-01"))
    assert "approved" in row
    assert "held" not in row


def test_evolution_log_shows_no_decision_when_the_audit_never_named_it(data_root: Path) -> None:
    _write_jsonl(
        data_root / "logs" / "insight-staged.jsonl",
        [{"ts": "2026-08-01T00:00+00:00", "name": "a", "description": "", "filename": "a.md"}],
    )
    out = wiki_render.render_evolution_log(data_root)
    row = next(line for line in out.splitlines() if line.startswith("2026-08-01"))
    assert "-" in row


def test_evolution_log_carries_superseded_by_from_the_archive(data_root: Path) -> None:
    _write_jsonl(
        data_root / "logs" / "insight-staged.jsonl",
        [{"ts": "2026-08-01T00:00+00:00", "name": "old", "description": "", "filename": "old.md"}],
    )
    archive = data_root / "skills" / ".archive"
    archive.mkdir(parents=True)
    (archive / "old.md").write_text(
        "---\nname: old\nsuperseded_by: new.md\n---\nbody\n", encoding="utf-8"
    )

    out = wiki_render.render_evolution_log(data_root)
    row = next(line for line in out.splitlines() if line.startswith("2026-08-01"))
    assert "new.md" in row


def test_evolution_log_counts_malformed_lines_and_keeps_going(data_root: Path) -> None:
    _write_jsonl(
        data_root / "logs" / "insight-staged.jsonl",
        [
            "{not json",
            {"ts": "2026-08-01T00:00+00:00", "name": "a", "description": "", "filename": "a.md"},
            {"name": "no-ts-no-filename"},
            "[1, 2, 3]",
        ],
    )
    _write_jsonl(
        data_root / "logs" / "audit.jsonl",
        ["}}}", {"ts": "2026-08-02T00:00:00+00:00", "path": "/x/a.md", "decision": "approved"}],
    )

    out = wiki_render.render_evolution_log(data_root)
    assert "a" in out
    assert "approved" in out
    # three unusable staged lines + one unusable audit line, named as such
    assert "4" in out
    assert "skipped" in out.lower()


def test_evolution_log_never_renders_a_control_character_from_a_log(data_root: Path) -> None:
    _write_jsonl(
        data_root / "logs" / "insight-staged.jsonl",
        [
            {
                "ts": "2026-08-01T00:00+00:00",
                "name": "a\nforged | row | here",
                "description": "",
                "filename": "a.md",
            }
        ],
    )
    out = wiki_render.render_evolution_log(data_root)
    body_rows = [line for line in out.splitlines() if line.startswith("2026-08-01")]
    assert len(body_rows) == 1
    assert "\n" not in body_rows[0]


# ------------------------------------------------------------- skill impact


def test_skill_impact_is_a_heading_when_there_is_no_selection_log(data_root: Path) -> None:
    out = wiki_render.render_skill_impact(data_root, since=None)
    assert out.strip()
    assert out == wiki_render.render_skill_impact(data_root, since=None)


def _selection_record(selected: list[str], catalog: list[str], **extra: object) -> dict:
    record = {
        "verdict": "judged",
        "enforced": True,
        "selected": selected,
        "selected_count": len(selected),
        "catalog_names": catalog,
    }
    record.update(extra)
    return record


def test_skill_impact_tallies_selections_last_date_and_judged_exposure(data_root: Path) -> None:
    logs = data_root / "logs"
    _write_jsonl(
        logs / "skill-selection-2026-08-01.jsonl",
        [
            _selection_record(["alpha"], ["alpha", "beta"]),
            _selection_record([], ["alpha", "beta"]),
        ],
    )
    _write_jsonl(
        logs / "skill-selection-2026-08-03.jsonl",
        [_selection_record(["alpha", "beta"], ["alpha", "beta"])],
    )

    out = wiki_render.render_skill_impact(data_root, since=None)
    alpha = next(line for line in out.splitlines() if line.startswith("alpha"))
    beta = next(line for line in out.splitlines() if line.startswith("beta"))

    assert "2" in alpha and "2026-08-03" in alpha and "3" in alpha
    assert "1" in beta and "2026-08-03" in beta


def test_skill_impact_counts_exposure_only_on_judged_records(data_root: Path) -> None:
    _write_jsonl(
        data_root / "logs" / "skill-selection-2026-08-01.jsonl",
        [
            _selection_record(["alpha"], ["alpha", "gamma"]),
            {
                "verdict": "fail_open_llm",
                "enforced": False,
                "selected": [],
                "catalog_names": ["gamma"],
            },
        ],
    )
    out = wiki_render.render_skill_impact(data_root, since=None)
    gamma = next(line for line in out.splitlines() if line.startswith("gamma"))
    # offered once on a judged record, never on the fail-open one
    assert gamma.split()[1:3] == ["0", "-"] or "1" in gamma


def test_skill_impact_honours_since(data_root: Path) -> None:
    logs = data_root / "logs"
    _write_jsonl(logs / "skill-selection-2026-07-01.jsonl", [_selection_record(["old"], ["old"])])
    _write_jsonl(logs / "skill-selection-2026-08-01.jsonl", [_selection_record(["new"], ["new"])])

    out = wiki_render.render_skill_impact(data_root, since=date(2026, 8, 1))
    assert "new" in out
    assert not any(line.startswith("old") for line in out.splitlines())


def test_skill_impact_never_reads_the_untrusted_body_fields(data_root: Path) -> None:
    _write_jsonl(
        data_root / "logs" / "skill-selection-2026-08-01.jsonl",
        [
            _selection_record(
                ["alpha"],
                ["alpha"],
                prompt_b64="c2VjcmV0LXByb21wdA==",
                output_b64="c2VjcmV0LW91dHB1dA==",
            )
        ],
    )
    out = wiki_render.render_skill_impact(data_root, since=None)
    assert "c2VjcmV0" not in out
    assert "secret" not in out


def test_skill_impact_counts_malformed_lines_and_keeps_going(data_root: Path) -> None:
    _write_jsonl(
        data_root / "logs" / "skill-selection-2026-08-01.jsonl",
        ["{oops", _selection_record(["alpha"], ["alpha"]), "null"],
    )
    out = wiki_render.render_skill_impact(data_root, since=None)
    assert "alpha" in out
    assert "2" in out
    assert "skipped" in out.lower()


def test_skill_impact_ignores_non_string_names(data_root: Path) -> None:
    _write_jsonl(
        data_root / "logs" / "skill-selection-2026-08-01.jsonl",
        [_selection_record([{"nested": 1}, "alpha"], ["alpha", 7])],  # type: ignore[list-item]
    )
    out = wiki_render.render_skill_impact(data_root, since=None)
    assert "alpha" in out
    assert "nested" not in out


# ------------------------------------------------------- the replay's window


def test_evolution_log_until_hides_later_candidates_without_calling_them_bad(
    data_root: Path,
) -> None:
    """RFC-0017 S4: a replayed July iteration must not read August's history."""
    _write_jsonl(
        data_root / "logs" / "insight-staged.jsonl",
        [
            {"ts": "2026-07-10T00:00+00:00", "name": "early", "filename": "early.md"},
            {"ts": "2026-08-20T00:00+00:00", "name": "later", "filename": "later.md"},
        ],
    )
    out = wiki_render.render_evolution_log(data_root, until=date(2026, 7, 31))
    assert "early" in out
    assert "later" not in out
    # Outside the window is not "unusable": the heading must not report a fault.
    assert "1 candidates, 0 unusable" in out


def test_evolution_log_until_defaults_to_the_whole_history(data_root: Path) -> None:
    _write_jsonl(
        data_root / "logs" / "insight-staged.jsonl",
        [{"ts": "2026-08-20T00:00+00:00", "name": "later", "filename": "later.md"}],
    )
    assert "later" in wiki_render.render_evolution_log(data_root)


def test_skill_impact_honours_until(data_root: Path) -> None:
    logs = data_root / "logs"
    _write_jsonl(logs / "skill-selection-2026-07-01.jsonl", [_selection_record(["old"], ["old"])])
    _write_jsonl(logs / "skill-selection-2026-08-01.jsonl", [_selection_record(["new"], ["new"])])

    out = wiki_render.render_skill_impact(data_root, since=None, until=date(2026, 7, 31))
    assert "old" in out
    assert not any(line.startswith("new") for line in out.splitlines())


def test_skill_impact_window_can_be_bounded_on_both_ends(data_root: Path) -> None:
    logs = data_root / "logs"
    for day, name in (("2026-07-01", "before"), ("2026-07-15", "inside"), ("2026-08-01", "after")):
        _write_jsonl(logs / f"skill-selection-{day}.jsonl", [_selection_record([name], [name])])

    out = wiki_render.render_skill_impact(
        data_root, since=date(2026, 7, 10), until=date(2026, 7, 20)
    )
    assert "inside" in out
    assert "before" not in out and "after" not in out
