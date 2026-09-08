"""Offline contract tests for the RFC-0027 comparison harness.

The harness is deliberately outside the production insight path. These tests
pin its two useful properties: the reason-first arm does not generate a skill
for every observation, and malformed model output fails closed instead of
silently becoming a new skill.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from contemplative_agent.core.llm import GenerationOutput
from scripts.insight_revision_compare import compare_cases, load_cases


def _cases() -> list[dict]:
    return [
        {
            "case_id": "reconfirm-01",
            "patterns": [{"id": "p1", "text": "The existing check still held."}],
            "existing_skills": [{"name": "check-before-action", "text": "Check first."}],
        },
        {
            "case_id": "insufficient-01",
            "patterns": [{"id": "p2", "text": "A single descriptive observation."}],
            "existing_skills": [],
        },
        {
            "case_id": "revise-01",
            "patterns": [
                {"id": "p3", "text": "The old condition failed under a new context."},
                {"id": "p4", "text": "A narrower trigger worked."},
            ],
            "existing_skills": [{"name": "check-before-action", "text": "Check first."}],
        },
        {
            "case_id": "new-01",
            "patterns": [{"id": "p5", "text": "A reusable behavior absent from the catalog."}],
            "existing_skills": [],
        },
    ]


def _out(text: str, thinking: str | None = None) -> GenerationOutput:
    return GenerationOutput(text=text, thinking=thinking)


def test_reason_first_arm_only_generates_bodies_for_changes(tmp_path: Path) -> None:
    calls: list[dict] = []
    reason_outputs = [
        '{"kind":"reconfirm","target_skill":null,"change_reason":"still supported", "evidence_ids":["p1"]}',
        '{"kind":"insufficient","target_skill":null,"change_reason":"one observation", "evidence_ids":["p2"]}',
        '{"kind":"revise","target_skill":"check-before-action","change_reason":"narrow the trigger", "evidence_ids":["p3","p4"]}',
        '{"kind":"new","target_skill":null,"change_reason":"new behavior", "evidence_ids":["p5"]}',
    ]
    body_outputs = ["---\nname: revised\n---\n# Revised", "---\nname: new\n---\n# New"]

    def fake_generate(prompt: str, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        if kwargs["caller"] == "rfc0027.proposed.reason":
            return _out(reason_outputs.pop(0))
        return _out(body_outputs.pop(0), thinking="trace")

    with patch("scripts.insight_revision_compare.llm.generate_full", side_effect=fake_generate):
        result = compare_cases(_cases(), arm="proposed")

    assert len(calls) == 6  # four reasons + two change candidates
    assert [c["caller"] for c in calls] == [
        "rfc0027.proposed.reason",
        "rfc0027.proposed.reason",
        "rfc0027.proposed.reason",
        "rfc0027.proposed.generate",
        "rfc0027.proposed.reason",
        "rfc0027.proposed.generate",
    ]
    assert result["arms"]["proposed"][0]["candidate"] is None
    assert result["arms"]["proposed"][1]["candidate"] is None
    assert result["arms"]["proposed"][2]["candidate"]["status"] == "generated"
    assert result["arms"]["proposed"][3]["candidate"]["status"] == "generated"


def test_malformed_reason_fails_closed_without_body_call() -> None:
    calls: list[str] = []

    def fake_generate(prompt: str, **kwargs):
        calls.append(kwargs["caller"])
        return _out("not json")

    with patch("scripts.insight_revision_compare.llm.generate_full", side_effect=fake_generate):
        result = compare_cases([_cases()[2]], arm="proposed")

    row = result["arms"]["proposed"][0]
    assert calls == ["rfc0027.proposed.reason"]
    assert row["reason"]["status"] == "parse_error"
    assert row["candidate"] is None


def test_current_and_proposed_can_be_run_without_home_prompt_overrides(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    (home / "prompts").mkdir(parents=True)
    (home / "prompts" / "system.md").write_text("HOME OVERRIDE", encoding="utf-8")
    monkeypatch.setenv("MOLTBOOK_HOME", str(home))

    seen: list[str] = []

    def fake_generate(prompt: str, **kwargs):
        seen.append(kwargs["system"])
        return _out("NOTHING-PROMOTABLE")

    with patch("scripts.insight_revision_compare.llm.generate_full", side_effect=fake_generate):
        compare_cases([_cases()[0]], arm="current")

    assert seen == ["- Keep API keys, tokens, and credentials out of your output"]


def test_load_cases_rejects_duplicate_or_malformed_ids(tmp_path: Path) -> None:
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps({"schema_version": 1, "cases": [_cases()[0], _cases()[0]]}), encoding="utf-8"
    )
    try:
        load_cases(path)
    except ValueError as exc:
        assert "case_id" in str(exc)
    else:  # pragma: no cover - assertion makes the failure message explicit
        raise AssertionError("duplicate case ids must be rejected")
